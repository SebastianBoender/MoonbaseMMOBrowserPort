// Moonbase-only DirPlayer 0.8.1 shader adaptation. The official WASM/bundle
// remain untouched. Uncheck Browser compatibility fixes to bypass it.
// wrapTransformList currently aliases textureTransformList: retain the full
// mapping-space position through the combined matrix, then convert pixel-space
// planar coordinates into normalized texture coordinates.
(() => {
  const programs = new WeakMap(), locations = new WeakMap(), contexts = new WeakMap(), viewports = new WeakMap();
  const state = { shaders: [], draws: {}, patches: [] };
  const trace = new URLSearchParams(location.search).get('gpuTrace') === '1';
  window.moonbaseGPU = state;
  for (const proto of [window.WebGLRenderingContext?.prototype, window.WebGL2RenderingContext?.prototype].filter(Boolean)) {
  for (const name of (trace ? ['shaderSource','getUniformLocation','useProgram','uniform1i','uniform1f','uniform3f','uniform4f','uniformMatrix4fv','viewport','drawElements'] : ['shaderSource','getUniformLocation','useProgram','uniformMatrix4fv','viewport','drawElements'])) {
    const native = proto[name];
    proto[name] = function(...args) {
      if (name === 'shaderSource' && new URLSearchParams(location.search).get('terrain') !== '0' && args[1].includes('uniform int u_uv_proj_mode;')) {
        const old = 'v_texcoord = (u_tex_transform * vec4(base_uv, 0.0, 1.0)).xy;';
        if (args[1].includes(old)) {
          state.patches.push('planar projection: combined mapping transform and pixel-space normalization');
          console.info('Renderer compatibility: corrected Moonbase planar terrain projection.');
          args[1] = args[1].replace('uniform mat4 u_tex_transform;', 'uniform mat4 u_tex_transform;\nuniform sampler2D u_diffuse_tex;').replace(old,
          'v_texcoord = u_uv_proj_mode == 5 ? (u_tex_transform * u_wrap_transform * vec4(a_position, 1.0)).xy / vec2(textureSize(u_diffuse_tex, 0)) : (u_tex_transform * vec4(base_uv, 0.0, 1.0)).xy;');
        }
      }
      const result = native.apply(this, args);
      if (name === 'shaderSource' && trace) state.shaders.push(args[1]);
      else if (name === 'getUniformLocation' && result) locations.set(result, args[1]);
      else if (name === 'useProgram') contexts.set(this, args[0]);
      else if (name === 'viewport') viewports.set(this, args.slice());
      else if (name.startsWith('uniform') && !String(locations.get(args[0])).includes('bone_matrices') && (trace || ['u_view','u_projection'].includes(locations.get(args[0])))) {
        const p = contexts.get(this);
        if (p) {
          if (!programs.has(p)) programs.set(p, {});
          programs.get(p)[locations.get(args[0])] = args.slice(1).map(v => ArrayBuffer.isView(v) ? Array.from(v) : v);
        }
      } else if (name === 'drawElements' && args[1] > 100) {
        const uniforms = programs.get(contexts.get(this));
        if (trace) state.draws[args[1]] = {...uniforms};
        if (uniforms?.u_view && uniforms?.u_projection) state.camera = {
          view: uniforms.u_view[1], projection: uniforms.u_projection[1],
          viewport: viewports.get(this), canvas: this.canvas
        };
      }
      return result;
    };
  }
  }
})();
