"""Small audited source patch against DirPlayer 0.8.1 commit 7f632b4.
The official runtime remains untouched; this patch is Modern-client only.
"""
from pathlib import Path
import sys


def replace(path, old, new):
    source = path.read_text()
    if source.count(old) != 1:
        raise ValueError(f'Upstream source changed: {path}: {old[:65]}')
    path.write_text(source.replace(old, new))


def apply(root):
    root = Path(root)
    stage = root / 'vm-rust/src/player/stage.rs'
    replace(stage, '''        compute_stage_layout(
            player.movie.rect.width() as f64,
            player.movie.rect.height() as f64,
            player.stage_size.0,
            player.stage_size.1,
            stretch_style(player),
        )''', '''        let mut layout = compute_stage_layout(
            player.movie.rect.width() as f64,
            player.movie.rect.height() as f64,
            player.stage_size.0,
            player.stage_size.1,
            stretch_style(player),
        );
        // Moonbase Modern: render pixels may grow, authored coordinates do not.
        if player.external_params.iter().any(|(k, v)| k == "moonbaseModern" && v == "1") {
            layout.stage_rect = [0.0, 0.0, player.movie.rect.width() as f64, player.movie.rect.height() as f64];
        }
        layout''')
    scene = root / 'vm-rust/src/rendering_gpu/webgl2/scene3d.rs'
    replace(scene, '''        // Unbind
        gl.bind_framebuffer(WebGl2RenderingContext::FRAMEBUFFER, None);
        gl.bind_texture(WebGl2RenderingContext::TEXTURE_2D, None);
        gl.bind_renderbuffer(WebGl2RenderingContext::RENDERBUFFER, None);

        self.fbo = Some(fbo);''', '''        // Keep the previous working target until the replacement is complete.
        let status = gl.check_framebuffer_status(WebGl2RenderingContext::FRAMEBUFFER);
        gl.bind_framebuffer(WebGl2RenderingContext::FRAMEBUFFER, None);
        gl.bind_texture(WebGl2RenderingContext::TEXTURE_2D, None);
        gl.bind_renderbuffer(WebGl2RenderingContext::RENDERBUFFER, None);
        if status != WebGl2RenderingContext::FRAMEBUFFER_COMPLETE {
            gl.delete_framebuffer(Some(&fbo));
            gl.delete_texture(Some(&texture));
            gl.delete_renderbuffer(Some(&depth_rb));
            return Err(JsValue::from_str("Moonbase Modern: incomplete 3D framebuffer"));
        }
        if let Some(old) = self.fbo.take() { gl.delete_framebuffer(Some(&old)); }
        if let Some(old) = self.fbo_texture.take() { gl.delete_texture(Some(&old)); }
        if let Some(old) = self.fbo_depth.take() { gl.delete_renderbuffer(Some(&old)); }
        self.fbo = Some(fbo);''')
    # Camera overlays retain authored coordinates, despite the larger viewport.
    replace(scene, '''        overlays: &[crate::player::cast_member::CameraOverlay],
        width: u32,
        height: u32,
    ) {''', '''        overlays: &[crate::player::cast_member::CameraOverlay],
        width: u32,
        height: u32,
        logical_width: f32,
        logical_height: f32,
    ) {''')
    # Limit replacement to this method (other passes have identical w/h locals).
    data = scene.read_text(); start = data.index('    pub fn render_overlays_to_fbo('); end = data.index('    // Old render_overlays_static',start)
    section = data[start:end].replace('let w = width as f32;', 'let w = logical_width;').replace('let h = height as f32;', 'let h = logical_height;')
    scene.write_text(data[:start]+section+data[end:])
    renderer = root / 'vm-rust/src/rendering_gpu/webgl2/mod.rs'
    replace(renderer, '''                                &self.context, &pass.member_key, overlays, width, height,
''', '''                                &self.context, &pass.member_key, overlays, width, height,
                                width as f32 / crate::player::stage::stage_scale(player).0 as f32,
                                height as f32 / crate::player::stage::stage_scale(player).1 as f32,
''')
    replace(renderer, '                    // Text member: render the text using specified font', '''                    // Modern text textures use logical source dimensions.
                    let modern_text = player.external_params.iter().any(|(k,v)| k == "moonbaseModern" && v == "1");
                    let (sx, sy) = crate::player::stage::stage_scale(player);
                    let sprite_rect = if modern_text { IntRect::from(
                        (sprite_rect.left as f64 / sx).round() as i32,
                        (sprite_rect.top as f64 / sy).round() as i32,
                        (sprite_rect.right as f64 / sx).round() as i32,
                        (sprite_rect.bottom as f64 / sy).round() as i32,
                    ) } else { sprite_rect.clone() };
                    // Text member: render the text using specified font''')
    # Legacy text is rasterized at authored size, then composited into the HD
    # stage. This avoids upstream's high-DPI field clipping and keeps its font.
    replace(renderer, '        let scale = scale_x.min(scale_y);', '''        let legacy_text = player.external_params.iter().any(|(k,v)| k == "moonbaseModern" && v == "1");
        let is_field = player.movie.cast_manager.find_member_by_ref(&cache_key.member_ref)
            .map(|m| matches!(m.member_type, CastMemberType::Field(_))).unwrap_or(false);
        let (width, height, wrap_width) = if legacy_text && is_field {
            ((width as f64 / scale_x).round().max(1.0) as u32,
             (height as f64 / scale_y).round().max(1.0) as u32,
             (wrap_width as f64 / scale_x).round().max(1.0) as u32)
        } else { (width, height, wrap_width) };
        let scale = if legacy_text { 1.0 } else { scale_x.min(scale_y) };''')
    replace(renderer, 'let actual_h = cached.height as i32;', '''let legacy_text = player.external_params.iter().any(|(k,v)| k == "moonbaseModern" && v == "1");
                    let actual_h = if legacy_text { (cached.height as f64 * crate::player::stage::stage_scale(player).1).round() as i32 } else { cached.height as i32 };''')
    replace(renderer, '                        Some((tex, _actual_w, actual_h)) => {', '''                        Some((tex, _actual_w, actual_h)) => {
                            let legacy_text = player.external_params.iter().any(|(k,v)| k == "moonbaseModern" && v == "1");
                            let actual_h = if legacy_text { (actual_h as f64 * crate::player::stage::stage_scale(player).1).round() as u32 } else { actual_h };''')
    replace(renderer, '(field_member.width as u32).min(width)', '''(if player.external_params.iter().any(|(k,v)| k == "moonbaseModern" && v == "1") {
                            (field_member.width as f64 * crate::player::stage::stage_scale(player).0).round() as u32
                        } else { field_member.width as u32 }).min(width)''')
    api = root / 'dirplayer-js-api/index.js'
    for name, argument, kind in [('onMovieLoaded','result','movie-loaded'), ('onFrameChanged','frame','frame'), ('onScriptError','err','script-error'), ('onScopeListChanged','scopeList','scope-list'), ('onDebugMessage','message','debug-message')]:
        old = f'export function {name}({argument}) {{'
        replace(api, old, old + f'\n  window.dispatchEvent(new CustomEvent("moonbase-runtime", {{detail: {{kind: "{kind}", value: {argument}}}}}));')



if __name__ == '__main__':
    apply(sys.argv[1])
