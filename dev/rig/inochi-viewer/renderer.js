import {deformParts} from './model.js';

function shader(gl, type, source) {
  const s = gl.createShader(type); gl.shaderSource(s, source); gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) { gl.deleteShader(s); throw Error('Could not compile the inspection renderer'); }
  return s;
}

export class RigRenderer {
  constructor(canvas, model, images) {
    this.canvas = canvas; this.model = model;
    const gl = this.gl = canvas.getContext('webgl', {alpha: true, antialias: true, premultipliedAlpha: true, preserveDrawingBuffer: true});
    if (!gl) throw Error('WebGL is unavailable. Try a browser with graphics acceleration enabled.');
    const program = this.program = gl.createProgram();
    const shaders = [shader(gl, gl.VERTEX_SHADER, `
      attribute vec2 a_position; attribute vec2 a_uv;
      uniform vec2 u_size; uniform float u_scale; uniform vec2 u_offset;
      varying vec2 v_uv;
      void main(){vec2 p=(a_position*u_scale+u_offset)/u_size;
        gl_Position=vec4(p.x*2.-1.,1.-p.y*2.,0.,1.);v_uv=a_uv;}`),
    shader(gl, gl.FRAGMENT_SHADER, `
      precision highp float; varying vec2 v_uv;
      uniform sampler2D u_texture; uniform sampler2D u_mask; uniform vec2 u_size;
      uniform float u_opacity; uniform float u_threshold; uniform bool u_maskPass; uniform bool u_masked;
      void main(){vec4 color=texture2D(u_texture,v_uv);
        if(u_maskPass){if(color.a<u_threshold)discard;gl_FragColor=vec4(1.);return;}
        if(u_masked && texture2D(u_mask,gl_FragCoord.xy/u_size).a<.5)discard;
        gl_FragColor=color*u_opacity;}`)];
    shaders.forEach(s => gl.attachShader(program, s)); gl.linkProgram(program); shaders.forEach(s => gl.deleteShader(s));
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw Error('Could not link the inspection renderer');
    gl.useProgram(program);
    this.uniforms = Object.fromEntries(['u_size', 'u_scale', 'u_offset', 'u_texture', 'u_mask', 'u_opacity', 'u_threshold', 'u_maskPass', 'u_masked'].map(n => [n, gl.getUniformLocation(program, n)]));
    this.position = gl.getAttribLocation(program, 'a_position'); this.uv = gl.getAttribLocation(program, 'a_uv');
    gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, true);
    gl.pixelStorei(gl.UNPACK_COLORSPACE_CONVERSION_WEBGL, gl.NONE);
    this.textures = images.map(img => {
      const texture = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, texture); this.textureOptions();
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, img); return texture;
    });
    this.meshes = new Map(model.puppet.nodes.children.filter(p => p.type === 'Part').map(p => {
      const positions = gl.createBuffer(), uv = gl.createBuffer(), indices = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, uv); gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(p.mesh.uvs), gl.STATIC_DRAW);
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, indices); gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, new Uint16Array(p.mesh.indices), gl.STATIC_DRAW);
      return [p.uuid, {positions, uv, indices, count: p.mesh.indices.length}];
    }));
    this.maskTexture = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, this.maskTexture); this.textureOptions();
    this.framebuffer = gl.createFramebuffer(); this.width = 0; this.height = 0;
  }
  textureOptions() {
    const gl = this.gl;
    for (const key of [gl.TEXTURE_MIN_FILTER, gl.TEXTURE_MAG_FILTER]) gl.texParameteri(gl.TEXTURE_2D, key, gl.LINEAR);
    for (const key of [gl.TEXTURE_WRAP_S, gl.TEXTURE_WRAP_T]) gl.texParameteri(gl.TEXTURE_2D, key, gl.CLAMP_TO_EDGE);
  }
  resize() {
    const gl = this.gl, rect = this.canvas.getBoundingClientRect(), dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = Math.max(1, Math.round(rect.width * dpr)), h = Math.max(1, Math.round(rect.height * dpr));
    if (w === this.width && h === this.height) return;
    this.canvas.width = this.width = w; this.canvas.height = this.height = h;
    gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, this.maskTexture);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, w, h, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.framebuffer);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, this.maskTexture, 0);
    if (gl.checkFramebufferStatus(gl.FRAMEBUFFER) !== gl.FRAMEBUFFER_COMPLETE) throw Error('Could not create the eye/mouth clipping surface');
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  }
  drawSurface(item) {
    const gl = this.gl, mesh = this.meshes.get(item.part.uuid);
    gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, this.textures[item.part.textures[0]]);
    gl.bindBuffer(gl.ARRAY_BUFFER, mesh.positions); gl.enableVertexAttribArray(this.position);
    gl.vertexAttribPointer(this.position, 2, gl.FLOAT, false, 0, 0);
    gl.bindBuffer(gl.ARRAY_BUFFER, mesh.uv); gl.enableVertexAttribArray(this.uv);
    gl.vertexAttribPointer(this.uv, 2, gl.FLOAT, false, 0, 0);
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, mesh.indices); gl.drawElements(gl.TRIANGLES, mesh.count, gl.UNSIGNED_SHORT, 0);
  }
  draw(values, zoom = 1, onlyPart = null) {
    const gl = this.gl; this.resize();
    const w = this.width, h = this.height, u = this.uniforms;
    gl.viewport(0, 0, w, h); gl.useProgram(this.program);
    const scale = Math.min(w / 1254, h / 1254) * zoom;
    gl.uniform2f(u.u_size, w, h); gl.uniform1f(u.u_scale, scale);
    gl.uniform2f(u.u_offset, (w - 1254 * scale) / 2, (h - 1254 * scale) / 2);
    gl.uniform1i(u.u_texture, 0); gl.uniform1i(u.u_mask, 1);
    gl.clearColor(0, 0, 0, 0); gl.bindFramebuffer(gl.FRAMEBUFFER, null); gl.clear(gl.COLOR_BUFFER_BIT);
    const items = deformParts(this.model, values), byId = new Map(items.map(i => [i.part.uuid, i]));
    for (const item of items) {
      gl.bindBuffer(gl.ARRAY_BUFFER, this.meshes.get(item.part.uuid).positions);
      gl.bufferData(gl.ARRAY_BUFFER, item.vertices, gl.DYNAMIC_DRAW);
    }
    // Inochi draws higher zsort first; equal values retain their saved ordering.
    items.sort((a, b) => (b.part.zsort ?? 0) - (a.part.zsort ?? 0));
    for (const item of items) {
      if ((onlyPart !== null && item.part.uuid !== onlyPart) || item.part.enabled === false || item.opacity < .0001) continue;
      const masks = item.part.masks ?? [];
      if (masks.length) {
        gl.bindFramebuffer(gl.FRAMEBUFFER, this.framebuffer); gl.disable(gl.BLEND); gl.clear(gl.COLOR_BUFFER_BIT);
        gl.uniform1i(u.u_maskPass, 1); gl.uniform1i(u.u_masked, 0);
        // Do not sample a texture while it is also the active render target.
        gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, null);
        for (const mask of masks) {
          const source = byId.get(mask.source); gl.uniform1f(u.u_threshold, source.part.mask_threshold ?? .5);
          this.drawSurface(source);
        }
        gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      }
      gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, this.maskTexture);
      gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
      gl.uniform1i(u.u_maskPass, 0); gl.uniform1i(u.u_masked, masks.length ? 1 : 0);
      gl.uniform1f(u.u_opacity, item.opacity); this.drawSurface(item);
    }
  }
  destroy() {
    const gl = this.gl;
    this.textures.forEach(t => gl.deleteTexture(t)); gl.deleteTexture(this.maskTexture);
    for (const mesh of this.meshes.values()) for (const k of ['positions', 'uv', 'indices']) gl.deleteBuffer(mesh[k]);
    gl.deleteFramebuffer(this.framebuffer); gl.deleteProgram(this.program);
  }
}
