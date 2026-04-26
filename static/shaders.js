// ─────────────────────────────────────────────────────────────────
// Interactive WebGL shader wallpapers
// Each shader is a fragment shader running in a fullscreen quad.
// Uniforms: uTime, uRes, uMouse, uMouseDown, uClicks (4 ripple drops)
// ─────────────────────────────────────────────────────────────────

const VERT = `
attribute vec2 aPos;
void main() { gl_Position = vec4(aPos, 0.0, 1.0); }
`;

// ─── 1. PLASMA FIELD ────────────────────────────────────────────
const FRAG_PLASMA = `
precision highp float;
uniform float uTime;
uniform vec2  uRes;
uniform vec2  uMouse;
uniform float uMouseDown;

void main(){
  vec2 uv = (gl_FragCoord.xy - 0.5*uRes) / min(uRes.x, uRes.y);
  vec2 m  = (uMouse - 0.5*uRes) / min(uRes.x, uRes.y);

  float t = uTime * 0.25;

  // Warp toward mouse
  vec2 d = uv - m;
  float r = length(d);
  uv += normalize(d + 0.0001) * 0.15 * exp(-r*2.5) * (0.6 + uMouseDown);

  float v = 0.0;
  v += sin(uv.x*3.0 + t);
  v += sin(uv.y*3.0 + t*1.3);
  v += sin((uv.x+uv.y)*2.5 + t*0.7);
  v += sin(length(uv*1.8 - vec2(sin(t*0.5), cos(t*0.4)))*4.0 + t);
  v *= 0.25;

  // Iso-band shading
  float band = smoothstep(0.0, 0.04, abs(fract(v*3.0 + t*0.1) - 0.5));

  vec3 a = vec3(0.04, 0.07, 0.10);
  vec3 b = vec3(0.10, 0.85, 0.78);   // cyan accent
  vec3 c = vec3(0.45, 0.20, 0.85);   // violet
  vec3 col = mix(a, b, smoothstep(-0.4, 0.6, v));
  col = mix(col, c, smoothstep(0.2, 0.9, sin(v*3.0 + t)*0.5+0.5)*0.35);
  col *= 0.55 + 0.45*band;

  // Mouse glow
  col += vec3(0.10, 0.85, 0.78) * exp(-r*r*30.0) * (0.5 + uMouseDown*1.2);

  gl_FragColor = vec4(col, 1.0);
}
`;

// ─── 2. VORONOI LATTICE ─────────────────────────────────────────
const FRAG_VORONOI = `
precision highp float;
uniform float uTime;
uniform vec2  uRes;
uniform vec2  uMouse;
uniform float uMouseDown;

vec2 hash22(vec2 p){
  p = vec2(dot(p,vec2(127.1,311.7)), dot(p,vec2(269.5,183.3)));
  return fract(sin(p)*43758.5453)*2.0-1.0;
}

void main(){
  vec2 uv = gl_FragCoord.xy / uRes.y;
  vec2 m  = uMouse / uRes.y;
  float t = uTime * 0.3;

  vec2 g  = uv * 9.0;
  vec2 gi = floor(g);
  vec2 gf = fract(g);

  float minD = 1e9;
  vec2  minPos = vec2(0.0);
  vec2  minCell = vec2(0.0);

  for(int y=-1;y<=1;y++){
    for(int x=-1;x<=1;x++){
      vec2 off = vec2(float(x), float(y));
      vec2 cell = gi + off;
      vec2 p = 0.5 + 0.5*sin(t + 6.2831*hash22(cell));
      vec2 r = off + p - gf;
      float d = dot(r,r);
      if(d < minD){ minD = d; minPos = r; minCell = cell; }
    }
  }

  // Distance to nearest cell EDGE (Voronoi edges)
  float minEdge = 1e9;
  for(int y=-2;y<=2;y++){
    for(int x=-2;x<=2;x++){
      vec2 off = vec2(float(x), float(y));
      vec2 cell = gi + off;
      vec2 p = 0.5 + 0.5*sin(t + 6.2831*hash22(cell));
      vec2 r = off + p - gf;
      vec2 diff = minPos - r;
      if(dot(diff,diff) > 1e-5){
        float e = dot(0.5*(minPos+r), normalize(r-minPos));
        minEdge = min(minEdge, e);
      }
    }
  }

  // Mouse proximity in same units
  float md = length(uv*9.0 - m*9.0 - minPos);   // approx — use cell distance
  vec2 cellWorld = (minCell + 0.5) / 9.0;
  float dm = distance(cellWorld, m);
  float hl = exp(-dm*8.0) * (0.4 + uMouseDown*1.5);

  vec3 base = vec3(0.025, 0.035, 0.05);
  vec3 acc  = vec3(0.10, 0.85, 0.78);
  vec3 col  = base + acc * hl;

  // Edge glow
  float edge = 1.0 - smoothstep(0.0, 0.04, minEdge);
  col += acc * edge * 0.6;

  // Cell-centre dots, faintly twinkling
  float dot1 = 1.0 - smoothstep(0.0, 0.06, sqrt(minD));
  col += acc * dot1 * (0.3 + 0.3*sin(t*2.0 + minCell.x*7.0 + minCell.y*3.0));

  gl_FragColor = vec4(col, 1.0);
}
`;

// ─── 3. RIPPLE POND ─────────────────────────────────────────────
const FRAG_RIPPLE = `
precision highp float;
uniform float uTime;
uniform vec2  uRes;
uniform vec2  uMouse;
uniform float uMouseDown;
uniform vec4  uClickX;   // up to 4 click positions x
uniform vec4  uClickY;   //                       y
uniform vec4  uClickT;   //                       start time (0 = unused)

float ripple(vec2 p, vec2 c, float age){
  if(age <= 0.0) return 0.0;
  float r = distance(p, c);
  float speed = 0.35;
  float wave  = sin(r*40.0 - age*8.0) * exp(-r*3.0) * exp(-age*0.9);
  // Only inside expanding wavefront
  float front = smoothstep(speed*age + 0.05, speed*age - 0.05, r);
  return wave * front;
}

void main(){
  vec2 uv = gl_FragCoord.xy / uRes.xy;
  float aspect = uRes.x / uRes.y;
  vec2 p = vec2(uv.x*aspect, uv.y);
  vec2 m = vec2((uMouse.x/uRes.x)*aspect, uMouse.y/uRes.y);

  float t = uTime;

  // Ambient ripple at mouse
  float h = sin(distance(p,m)*30.0 - t*4.0) * exp(-distance(p,m)*4.0) * 0.25;

  // Click ripples
  for(int i=0;i<4;i++){
    float ct = uClickT[i];
    if(ct > 0.0){
      vec2 cp = vec2((uClickX[i]/uRes.x)*aspect, uClickY[i]/uRes.y);
      h += ripple(p, cp, t - ct) * 1.2;
    }
  }

  // Cross-hatched caustics from height field gradient (cheap)
  float dx = h - sin(distance(p+vec2(0.005,0.0),m)*30.0 - t*4.0)*exp(-distance(p+vec2(0.005,0.0),m)*4.0)*0.25;
  float caustic = pow(abs(h)*4.0 + 0.05, 0.6);

  vec3 deep = vec3(0.02, 0.04, 0.07);
  vec3 mid  = vec3(0.05, 0.18, 0.28);
  vec3 hi   = vec3(0.30, 0.95, 0.85);

  vec3 col = mix(deep, mid, caustic);
  col += hi * smoothstep(0.15, 0.4, abs(h)) * 0.9;

  // Subtle vignette
  vec2 vc = uv - 0.5;
  col *= 1.0 - dot(vc,vc)*0.7;

  gl_FragColor = vec4(col, 1.0);
}
`;

// ─── 4. PARTICLE CONSTELLATION ──────────────────────────────────
const FRAG_PARTICLES = `
precision highp float;
uniform float uTime;
uniform vec2  uRes;
uniform vec2  uMouse;
uniform float uMouseDown;

float hash11(float n){ return fract(sin(n)*43758.5453); }

void main(){
  vec2 uv = (gl_FragCoord.xy - 0.5*uRes) / min(uRes.x,uRes.y);
  vec2 m  = (uMouse - 0.5*uRes) / min(uRes.x,uRes.y);
  float t = uTime;

  vec3 col = vec3(0.02, 0.03, 0.05);

  // Background nebula
  float neb = sin(uv.x*1.5 + t*0.1)*sin(uv.y*1.3 - t*0.07);
  col += vec3(0.04, 0.10, 0.14) * (neb*0.5+0.5) * 0.4;

  const int N = 60;
  for(int i=0;i<N;i++){
    float fi = float(i);
    float seed = hash11(fi*1.37);

    // Each particle orbits a base position, pulled toward mouse
    float ang = t*(0.2 + seed*0.6) + seed*6.28;
    float rad = 0.15 + 0.55*hash11(fi*2.31);
    vec2 base = vec2(cos(ang)*rad, sin(ang*1.13 + seed*3.0)*rad*0.9);

    // Mouse attraction
    vec2 toM = m - base;
    float pull = 0.35 + uMouseDown*0.6;
    vec2 pos = base + toM * pull * (0.4 + 0.6*hash11(fi*0.71));

    float d = distance(uv, pos);
    float size = 0.0025 + hash11(fi*4.1)*0.0035;
    float bright = size / max(d, 0.0008);
    bright *= 0.9 + 0.4*sin(t*2.0 + seed*10.0);

    vec3 hue = mix(vec3(0.10,0.85,0.78), vec3(0.55,0.40,0.95), hash11(fi*0.51));
    col += hue * bright * 0.4;
  }

  // Mouse halo
  float md = length(uv - m);
  col += vec3(0.10,0.85,0.78) * exp(-md*md*8.0) * (0.15 + uMouseDown*0.6);

  gl_FragColor = vec4(col, 1.0);
}
`;

// ─── 5. FLOW FIELD ──────────────────────────────────────────────
const FRAG_FLOW = `
precision highp float;
uniform float uTime;
uniform vec2  uRes;
uniform vec2  uMouse;
uniform float uMouseDown;

float hash(vec2 p){ return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453); }
float noise(vec2 p){
  vec2 i = floor(p), f = fract(p);
  vec2 u = f*f*(3.0-2.0*f);
  return mix(mix(hash(i), hash(i+vec2(1,0)), u.x),
             mix(hash(i+vec2(0,1)), hash(i+vec2(1,1)), u.x), u.y);
}
float fbm(vec2 p){
  float v=0.0, a=0.5;
  for(int i=0;i<5;i++){ v += a*noise(p); p*=2.0; a*=0.5; }
  return v;
}

void main(){
  vec2 uv = gl_FragCoord.xy / uRes.y;
  vec2 m  = uMouse / uRes.y;
  float t = uTime * 0.15;

  // Flow direction from fbm, biased by mouse
  vec2 p = uv*1.8 + vec2(t*0.3, -t*0.2);
  float a = fbm(p) * 6.2831;
  vec2 flow = vec2(cos(a), sin(a));

  // Mouse "fan" — push flow outward from cursor
  vec2 toM = uv - m;
  float dM = length(toM);
  flow = mix(flow, normalize(toM+0.0001), exp(-dM*4.0)*(0.6+uMouseDown));

  // Trace short streaks
  float streak = 0.0;
  vec2 q = uv;
  for(int i=0;i<14;i++){
    float fi = float(i)/14.0;
    vec2 pp = q - flow*fi*0.04;
    float seed = hash(floor(pp*60.0));
    streak += step(0.985, seed) * (1.0 - fi);
  }

  vec3 base = vec3(0.025, 0.04, 0.06);
  vec3 hi   = vec3(0.10, 0.85, 0.78);
  vec3 warm = vec3(0.95, 0.55, 0.25);

  // Heat map by flow angle
  float hue = sin(a*0.5)*0.5+0.5;
  vec3 col  = base + mix(hi, warm, hue) * streak * 0.55;

  // Mouse glow
  col += hi * exp(-dM*dM*15.0) * (0.3 + uMouseDown*1.2);

  // Field-line shading
  col += hi * smoothstep(0.45,0.55,fbm(uv*5.0+flow*0.5+t)) * 0.08;

  gl_FragColor = vec4(col, 1.0);
}
`;

const SHADERS = {
  plasma:    { name: 'Plasma Field',         frag: FRAG_PLASMA,    desc: 'Flowing neon iso-curves. Cursor warps the field.' },
  voronoi:   { name: 'Voronoi Lattice',      frag: FRAG_VORONOI,   desc: 'Animated cellular grid. Cells brighten near cursor.' },
  ripple:    { name: 'Ripple Pond',          frag: FRAG_RIPPLE,    desc: 'Click anywhere to drop a ripple.' },
  particles: { name: 'Particle Constellation', frag: FRAG_PARTICLES, desc: '60 orbiting particles drawn toward your cursor.' },
  flow:      { name: 'Flow Field',           frag: FRAG_FLOW,      desc: 'Vector field of streaks. Cursor bends the flow.' },
};

// ── WebGL renderer ──
class ShaderWallpaper {
  constructor(canvas){
    this.canvas = canvas;
    this.gl = canvas.getContext('webgl', { antialias: false, premultipliedAlpha: false });
    if (!this.gl) throw new Error('WebGL unavailable');
    this.mouse = [0,0];
    this.targetMouse = [0,0];
    this.mouseDown = 0;
    this.targetMouseDown = 0;
    this.clicks = [];   // {x,y,t}
    this.t0 = performance.now()/1000;
    this.current = null;
    this._buildQuad();
    this._bindEvents();
    this.resize();
    this._loop();
  }

  _buildQuad(){
    const gl = this.gl;
    const vbo = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, vbo);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 1,-1, -1,1, 1,1]), gl.STATIC_DRAW);
  }

  _compile(src, type){
    const gl = this.gl;
    const sh = gl.createShader(type);
    gl.shaderSource(sh, src);
    gl.compileShader(sh);
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
      console.error('Shader error:', gl.getShaderInfoLog(sh), '\n', src);
      throw new Error('Shader compile failed');
    }
    return sh;
  }

  use(key){
    const gl = this.gl;
    const def = SHADERS[key];
    if (!def) return;
    if (this.program) gl.deleteProgram(this.program);
    const vs = this._compile(VERT, gl.VERTEX_SHADER);
    const fs = this._compile(def.frag, gl.FRAGMENT_SHADER);
    const p = gl.createProgram();
    gl.attachShader(p, vs); gl.attachShader(p, fs);
    gl.bindAttribLocation(p, 0, 'aPos');
    gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) {
      console.error('Link error', gl.getProgramInfoLog(p));
      throw new Error('Program link failed');
    }
    this.program = p;
    this.uniforms = {
      uTime:      gl.getUniformLocation(p, 'uTime'),
      uRes:       gl.getUniformLocation(p, 'uRes'),
      uMouse:     gl.getUniformLocation(p, 'uMouse'),
      uMouseDown: gl.getUniformLocation(p, 'uMouseDown'),
      uClickX:    gl.getUniformLocation(p, 'uClickX'),
      uClickY:    gl.getUniformLocation(p, 'uClickY'),
      uClickT:    gl.getUniformLocation(p, 'uClickT'),
    };
    this.current = key;
    gl.useProgram(p);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
  }

  _bindEvents(){
    const onMove = e => {
      const r = this.canvas.getBoundingClientRect();
      const x = (e.clientX ?? (e.touches?.[0]?.clientX || 0)) - r.left;
      const y = r.height - ((e.clientY ?? (e.touches?.[0]?.clientY || 0)) - r.top);
      this.targetMouse[0] = x * (this.canvas.width / r.width);
      this.targetMouse[1] = y * (this.canvas.height / r.height);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('touchmove', onMove, { passive: true });
    window.addEventListener('mousedown', e => {
      this.targetMouseDown = 1;
      this._addClick(e);
    });
    window.addEventListener('mouseup', () => { this.targetMouseDown = 0; });
    window.addEventListener('touchstart', e => {
      this.targetMouseDown = 1;
      this._addClick(e.touches[0]);
    });
    window.addEventListener('touchend', () => { this.targetMouseDown = 0; });
    window.addEventListener('resize', () => this.resize());
  }

  _addClick(e){
    const r = this.canvas.getBoundingClientRect();
    const x = (e.clientX - r.left) * (this.canvas.width / r.width);
    const y = (r.height - (e.clientY - r.top)) * (this.canvas.height / r.height);
    const t = performance.now()/1000 - this.t0;
    this.clicks.push({ x, y, t });
    if (this.clicks.length > 4) this.clicks.shift();
  }

  resize(){
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = Math.floor(window.innerWidth * dpr);
    const h = Math.floor(window.innerHeight * dpr);
    if (this.canvas.width !== w || this.canvas.height !== h){
      this.canvas.width = w; this.canvas.height = h;
    }
    this.gl.viewport(0, 0, w, h);
  }

  _loop(){
    const gl = this.gl;
    const tick = () => {
      if (!this.program) { requestAnimationFrame(tick); return; }
      // Smooth mouse
      this.mouse[0] += (this.targetMouse[0] - this.mouse[0]) * 0.18;
      this.mouse[1] += (this.targetMouse[1] - this.mouse[1]) * 0.18;
      this.mouseDown += (this.targetMouseDown - this.mouseDown) * 0.15;

      const t = performance.now()/1000 - this.t0;

      gl.useProgram(this.program);
      gl.uniform1f(this.uniforms.uTime, t);
      gl.uniform2f(this.uniforms.uRes,  this.canvas.width, this.canvas.height);
      gl.uniform2f(this.uniforms.uMouse, this.mouse[0], this.mouse[1]);
      gl.uniform1f(this.uniforms.uMouseDown, this.mouseDown);

      // Pack click history
      const cx = [0,0,0,0], cy = [0,0,0,0], ct = [0,0,0,0];
      for (let i=0;i<this.clicks.length;i++){
        cx[i] = this.clicks[i].x;
        cy[i] = this.clicks[i].y;
        ct[i] = this.clicks[i].t;
      }
      if (this.uniforms.uClickX) gl.uniform4fv(this.uniforms.uClickX, cx);
      if (this.uniforms.uClickY) gl.uniform4fv(this.uniforms.uClickY, cy);
      if (this.uniforms.uClickT) gl.uniform4fv(this.uniforms.uClickT, ct);

      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }
}

window.SHADERS = SHADERS;
window.ShaderWallpaper = ShaderWallpaper;
