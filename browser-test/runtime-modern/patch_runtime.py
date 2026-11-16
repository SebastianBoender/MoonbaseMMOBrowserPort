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
    api = root / 'dirplayer-js-api/index.js'
    for name, argument, kind in [('onMovieLoaded','result','movie-loaded'), ('onFrameChanged','frame','frame'), ('onScriptError','err','script-error'), ('onScopeListChanged','scopeList','scope-list'), ('onDebugMessage','message','debug-message')]:
        old = f'export function {name}({argument}) {{'
        replace(api, old, old + f'\n  window.dispatchEvent(new CustomEvent("moonbase-runtime", {{detail: {{kind: "{kind}", value: {argument}}}}}));')



if __name__ == '__main__':
    apply(sys.argv[1])
