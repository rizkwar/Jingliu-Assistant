// Accessories drawn over a Live2D model: glasses. They are rigged like an art mesh inside her face's
// warp deformer: shaped once on her face at rest, then carried by her face mesh every frame (see
// faceLayout), so they turn, tilt and look up and down exactly as her face does. Without a face mesh
// they fall back to a small 3D model of her head (glassesLayout with a pose).
// Geometry is separate from drawing, so it can be checked without a renderer.

export const GLASSES_STYLES = ['teacher', 'round', 'rectangle', 'oval', 'halfrim'];
export const FRAME_COLORS = {gold: 0xc9a467, silver: 0xb4bfcf, black: 0x24252c, ice: 0x8cc4ff, crimson: 0xc8475f};
export const LENS_TINTS = {
  clear: {color: 0xeef6ff, alpha: .05}, moon: {color: 0x7fb3ff, alpha: .18},
  rose: {color: 0xff9db4, alpha: .16}, dark: {color: 0x0b0f18, alpha: .7},
};
// Her head, in units of half the distance between her eyes, with the eyes at (±1, 0, 0) and +z toward
// the viewer: the glasses sit in front of the eyes, the nose tip further forward.
const GLASS_DEPTH = .36, NOSE_DEPTH = 1.05, WRAP = .2, ARM_LENGTH = 1.15, FOCAL = 9;
// The lenses sit a touch nearer her nose than her eyes do, so their outer edges stay on her face.
const LENS_X = .93;
// Each style, in head units: lens half-width and half-height, how far below the eyes it sits, the lens
// shape and the wire's thickness. Anime glasses are big: wider than her eyes, nearly meeting over her nose.
const STYLES = {
  teacher:   {halfW: .68, halfH: .41, drop: .1, shape: 'panto', weight: .03, ornament: true},
  round:     {halfW: .58, halfH: .55, drop: .06, shape: 'ellipse', weight: .034},
  oval:      {halfW: .7, halfH: .44, drop: .06, shape: 'ellipse', weight: .034},
  rectangle: {halfW: .7, halfH: .4, drop: .06, shape: 'rect', weight: .034},
  halfrim:   {halfW: .7, halfH: .42, drop: .06, shape: 'rect', weight: .028, brow: true},
};

const rotate = (x, y, angle) => [x * Math.cos(angle) - y * Math.sin(angle), x * Math.sin(angle) + y * Math.cos(angle)];

function eyeCenter(eye) {
  const width = Math.max(1, eye.right - eye.left);
  // The lower lid barely moves when she blinks, so the eye's centre is measured up from it.
  return {x: (eye.left + eye.right) / 2, y: eye.bottom - width * .36};
}

/** How her head is turned and how big it is on screen, from her eyes (and nose, when known).
 * `pose`: {nose: {x, y}} in screen pixels, and/or {yaw, pitch} in radians. */
export function headPose(eyes, pose = {}) {
  if (!eyes || eyes.length !== 2) return null;
  const [a, b] = [...eyes].sort((p, q) => (p.left + p.right) - (q.left + q.right)).map(eyeCenter);
  const dx = b.x - a.x, dy = b.y - a.y, half = Math.hypot(dx, dy) / 2;
  if (half < 1) return null;
  const roll = Math.atan2(dy, dx), origin = {x: (a.x + b.x) / 2, y: (a.y + b.y) / 2};
  let yaw = pose.yaw ?? 0;
  if (pose.nose) {
    // The nose tip sits in front of the eyes: how far it shifts sideways says how far she has turned.
    const [offset] = rotate(pose.nose.x - origin.x, pose.nose.y - origin.y, -roll);
    yaw = Math.atan2(offset, NOSE_DEPTH * half);
  }
  yaw = Math.max(-.8, Math.min(.8, yaw));
  const pitch = Math.max(-.5, Math.min(.5, pose.pitch ?? 0));
  return {origin, roll, yaw, pitch, scale: half / Math.cos(yaw)};
}

/** Where the glasses are: each lens's outline, the bridge, end pieces and the visible arm. Facing
 * forward (no pose) this is the glasses as shaped on her face at rest. */
export function glassesLayout(eyes, style = 'teacher', pose = {}) {
  const head = headPose(eyes, pose);
  if (!head) return null;
  const {origin, roll, yaw, pitch, scale} = head;
  const spec = STYLES[style] ?? STYLES.teacher;
  const {halfW, halfH, drop} = spec;
  const project = ([x, y, z]) => {
    const x1 = x * Math.cos(yaw) + z * Math.sin(yaw), z1 = -x * Math.sin(yaw) + z * Math.cos(yaw);
    const y2 = y * Math.cos(pitch) - z1 * Math.sin(pitch), z2 = y * Math.sin(pitch) + z1 * Math.cos(pitch);
    const near = FOCAL / (FOCAL - z2);                   // A little perspective: nearer parts are larger.
    const [rx, ry] = rotate(x1 * near * scale, y2 * near * scale, roll);
    return {x: origin.x + rx, y: origin.y + ry};
  };
  const lenses = [-1, 1].map(side => {
    // A lens point from (outward, down) on its own plane; the plane wraps back toward her temple.
    const point = (out, v) => project([side * (LENS_X + out * Math.cos(WRAP)), drop + v,
                                       GLASS_DEPTH - Math.max(0, out) * Math.sin(WRAP)]);
    return measured({side, point, halfW, halfH, center: point(0, 0),
                     outline: shapeOutline(spec).map(([out, v]) => point(out, v)),
                     brow: spec.brow ? topEdge(spec).map(([out, v]) => point(out, v)) : null,
                     ornament: spec.ornament ? ornament(spec).map(part => part.map(([out, v]) => point(out, v))) : null,
                     hinge: point(halfW * .99, -halfH * .5)});
  });
  const [left, right] = lenses;
  // The bridge: a fine wire arching over her nose between the lenses' upper inner corners.
  const bridge = [left.point(-halfW * .97, -halfH * .3), project([0, drop - halfH * .95, GLASS_DEPTH + .08]),
                  right.point(-halfW * .97, -halfH * .3)];
  // Only the arm on the side turned toward the viewer shows; the other runs behind her head.
  const arms = [];
  for (const lens of lenses) {
    if (-lens.side * yaw <= .06) continue;              // > 0 when this side of her head faces the viewer.
    const end = project([lens.side * (LENS_X + halfW * Math.cos(WRAP) + .08), drop - halfH * .4,
                         GLASS_DEPTH - halfW * Math.sin(WRAP) - ARM_LENGTH]);
    arms.push([lens.hinge, end]);
  }
  return {origin, roll, yaw, pitch, scale, lenses, bridge, arms, line: Math.max(1, scale * spec.weight)};
}

function measured(lens) {
  const xs = lens.outline.map(p => p.x), ys = lens.outline.map(p => p.y);
  return {...lens, width: Math.max(...xs) - Math.min(...xs), height: Math.max(...ys) - Math.min(...ys)};
}

/** The glasses carried by her face, as an art mesh in her face's warp deformer is.
 * `restEyes`: her eyes with her face at rest; `follow(point)`: where a point of her face at rest is
 * now. `pose` {yaw, pitch}: her turn, for the little extra the glasses move, being in front of her face,
 * and for which arm shows. */
export function faceLayout(restEyes, style, follow, pose = {}) {
  const rest = glassesLayout(restEyes, style);
  if (!rest) return null;
  const yaw = Math.max(-.8, Math.min(.8, pose.yaw ?? 0)), pitch = Math.max(-.5, Math.min(.5, pose.pitch ?? 0));
  const half = rest.scale;
  // Parallax: being in front of her face, the glasses swing a little further than it when she turns.
  const shiftX = Math.sin(yaw) * GLASS_DEPTH * half, shiftY = -Math.sin(pitch) * GLASS_DEPTH * half;
  const move = p => follow({x: p.x + shiftX, y: p.y + shiftY});
  // The near arm runs back from its hinge toward her ear, longer the further she turns.
  const arms = [];
  for (const lens of rest.lenses) {
    const facing = -lens.side * yaw;
    if (facing <= .06) continue;
    arms.push([lens.hinge, {x: lens.hinge.x + lens.side * Math.sin(facing) * ARM_LENGTH * half,
                            y: lens.hinge.y + .06 * half}]);
  }
  // Her face's size now, measured up and down (which turning does not shorten), sets the wire's width.
  const top = move({x: rest.origin.x, y: rest.origin.y - half}), bottom = move({x: rest.origin.x, y: rest.origin.y + half});
  const size = Math.hypot(bottom.x - top.x, bottom.y - top.y) / (2 * half);
  return {origin: move(rest.origin), roll: Math.atan2(bottom.x - top.x, bottom.y - top.y) * -1, yaw, pitch,
          scale: half * size, line: Math.max(1, rest.line * size),
          lenses: rest.lenses.map(lens => measured({
            side: lens.side, halfW: lens.halfW, halfH: lens.halfH, point: (out, v) => move(lens.point(out, v)),
            center: move(lens.center), hinge: move(lens.hinge), outline: lens.outline.map(move),
            brow: lens.brow?.map(move) ?? null, ornament: lens.ornament?.map(part => part.map(move)) ?? null})),
          bridge: rest.bridge.map(move), arms: arms.map(arm => arm.map(move))};
}

/** A warp deformer: a grid of points pinned to a mesh. `nodes[row][column]` are where the grid's
 * points are now; the grid spanned `box` {left, top, width, height} at rest. Returns follow(point). */
export function latticeWarp(box, nodes) {
  const rows = nodes.length - 1, columns = nodes[0].length - 1;
  return ({x, y}) => {
    // Points beyond the grid carry on along its edge cells.
    const u = (x - box.left) / box.width * columns, v = (y - box.top) / box.height * rows;
    const i = Math.max(0, Math.min(columns - 1, Math.floor(u))), j = Math.max(0, Math.min(rows - 1, Math.floor(v)));
    const s = u - i, t = v - j;
    const [a, b, c, d] = [nodes[j][i], nodes[j][i + 1], nodes[j + 1][i], nodes[j + 1][i + 1]];
    return {x: (a.x * (1 - s) + b.x * s) * (1 - t) + (c.x * (1 - s) + d.x * s) * t,
            y: (a.y * (1 - s) + b.y * s) * (1 - t) + (c.y * (1 - s) + d.y * s) * t};
  };
}

/** Pins a point to a triangle mesh: the triangle it lies in (or the nearest), and its weights there,
 * so pinned(...) can place it again however the mesh has moved. `meshes`: [{vertices, indices}]. */
export function pinToMesh({x, y}, meshes) {
  let best = null;
  meshes.forEach((mesh, which) => {
    const {vertices: p, indices} = mesh;
    for (let k = 0; k + 2 < indices.length; k += 3) {
      const [a, b, c] = [indices[k], indices[k + 1], indices[k + 2]];
      const ax = p[a * 2], ay = p[a * 2 + 1], bx = p[b * 2], by = p[b * 2 + 1], cx = p[c * 2], cy = p[c * 2 + 1];
      const area = (bx - ax) * (cy - ay) - (cx - ax) * (by - ay);
      if (Math.abs(area) < 1e-9) continue;
      const wb = ((x - ax) * (cy - ay) - (cx - ax) * (y - ay)) / area;
      const wc = ((bx - ax) * (y - ay) - (x - ax) * (by - ay)) / area;
      const wa = 1 - wb - wc;
      // Inside: no weight below zero. Outside: how far outside, to pick the nearest triangle.
      const miss = Math.max(0, -wa, -wb, -wc);
      if (!best || miss < best.miss) best = {mesh: which, vertices: [a, b, c], weights: [wa, wb, wc], miss};
    }
  });
  return best;
}

/** Where a pinned point is, given each mesh's vertices now. */
export function pinned(pin, vertices) {
  const p = vertices[pin.mesh];
  let x = 0, y = 0;
  pin.vertices.forEach((vertex, k) => {x += p[vertex * 2] * pin.weights[k]; y += p[vertex * 2 + 1] * pin.weights[k];});
  return {x, y};
}

function shapeOutline({shape, halfW, halfH}) {
  // Points as [outward, down]. A superellipse: low exponents are round, high ones boxy.
  const points = [];
  for (let i = 0; i < 64; i++) {
    const t = (i / 64) * Math.PI * 2, c = Math.cos(t), s = Math.sin(t);
    const power = {ellipse: 2, rect: 5}[shape] ?? (s < 0 ? 3.6 : 2.3);  // Panto: a flat top, a round bottom.
    let out = halfW * Math.sign(c) * Math.abs(c) ** (2 / power), v = halfH * Math.sign(s) * Math.abs(s) ** (2 / power);
    if (shape === 'panto') {
      if (v < 0) v -= halfH * .08 * (out / halfW);         // The top edge lifts toward her temple…
      if (v > 0 && out < 0) out *= 1 - .16 * (v / halfH);  // …and the lens tucks in under the bridge.
    }
    points.push([out, v]);
  }
  return points;
}

function topEdge({halfW, halfH}) {
  // The half-rim's brow bar: the top edge with the start of each corner.
  return shapeOutline({shape: 'rect', halfW, halfH}).filter(([, v]) => v < -halfH * .55);
}

function ornament({halfW, halfH}) {
  // The filigree end piece on each lens's outer corner: a small leaf swept up and out, a smaller one
  // curling down, both growing out of the rim itself.
  const x = halfW * .96, y = -halfH * .55;
  return [
    [[x - .04, y + .01], [x + .02, y - .09], [x + .09, y - .1], [x + .07, y - .03], [x + .02, y + .03]],
    [[x, y + .03], [x + .06, y + .05], [x + .07, y + .12], [x + .02, y + .09]],
  ];
}

const polyline = (graphics, points, close = false) => {
  graphics.moveTo(points[0].x, points[0].y);
  for (const p of points.slice(1)) graphics.lineTo(p.x, p.y);
  if (close) graphics.lineTo(points[0].x, points[0].y);
};

/** Draws glasses laid out by glassesLayout or faceLayout into a PIXI.Graphics (cleared each frame).
 * `options`: {style, frame, lens}. */
export function drawGlasses(graphics, layout, options = {}) {
  graphics.clear();
  graphics.visible = Boolean(layout);
  if (!layout) return null;
  graphics.position.set(0, 0);
  graphics.rotation = 0;
  const frame = FRAME_COLORS[options.frame] ?? FRAME_COLORS.gold;
  const tint = LENS_TINTS[options.lens] ?? LENS_TINTS.clear;
  const line = layout.line, ink = shade(frame, .45);
  const brow = layout.lenses.some(lens => lens.brow);
  const [shadowX, shadowY] = rotate(0, line * 2.2, layout.roll);
  // 1. The faintest shadow the lower rims cast on her cheeks.
  graphics.lineStyle(line * 1.6, 0x6a4a6a, .05);
  for (const lens of layout.lenses)
    polyline(graphics, lens.outline.filter((p, i) => i > 6 && i < 26).map(p => ({x: p.x + shadowX, y: p.y + shadowY})));
  // 2. The glass: a tint, and two short glints across its upper outer part, as anime glasses catch the light.
  for (const lens of layout.lenses) {
    graphics.lineStyle(0);
    graphics.beginFill(tint.color, tint.alpha);
    graphics.drawPolygon(lens.outline.flatMap(p => [p.x, p.y]));
    graphics.endFill();
    const glint = (o0, v0, o1, v1) => [lens.point(o0 * lens.halfW, v0 * lens.halfH), lens.point(o1 * lens.halfW, v1 * lens.halfH)];
    graphics.lineStyle(line * 2.6, 0xffffff, .16);
    polyline(graphics, glint(.18, -.1, .5, -.68));
    graphics.lineStyle(line * 1.1, 0xffffff, .22);
    polyline(graphics, glint(.5, .05, .68, -.3));
  }
  // 3. The wire: a soft darker edge, the metal, then a fine highlight along the upper rims.
  const wire = (width, color, alpha) => {
    graphics.lineStyle(width * (brow ? .6 : 1), color, alpha);
    for (const lens of layout.lenses) polyline(graphics, lens.outline, true);
    if (brow) {
      graphics.lineStyle(width * 2, color, alpha);
      for (const lens of layout.lenses) polyline(graphics, lens.brow);
    }
    graphics.lineStyle(width, color, alpha);
    const [from, control, to] = layout.bridge;
    graphics.moveTo(from.x, from.y);
    graphics.quadraticCurveTo(control.x, control.y, to.x, to.y);
    graphics.lineStyle(width * .9, color, alpha);
    for (const arm of layout.arms) polyline(graphics, arm);
  };
  wire(line + 1.4, ink, .7);
  wire(line, frame, 1);
  graphics.lineStyle(Math.max(.6, line * .35), shade(frame, -.6), .8);
  for (const lens of layout.lenses) polyline(graphics, lens.outline.filter((p, i) => i > 36 && i < 60));
  // 4. The end pieces on the outer corners: filigree leaves (teacher), or a small hinge.
  for (const lens of layout.lenses) {
    if (-lens.side * layout.yaw < -.12) continue;      // Turned well away, behind her head.
    if (lens.ornament) {
      for (const leaf of lens.ornament) {
        graphics.lineStyle(Math.max(.8, line * .7), ink, .6);
        graphics.beginFill(frame, 1);
        graphics.drawPolygon(leaf.flatMap(p => [p.x, p.y]));
        graphics.endFill();
      }
      graphics.lineStyle(0);
      graphics.beginFill(shade(frame, -.7), .9);
      graphics.drawCircle(lens.hinge.x, lens.hinge.y, line * .9);
      graphics.endFill();
    } else {
      graphics.lineStyle(Math.max(.8, line * .6), ink, .6);
      graphics.beginFill(frame, 1);
      graphics.drawCircle(lens.hinge.x, lens.hinge.y, line * 1.2);
      graphics.endFill();
    }
  }
  return layout;
}

function shade(color, amount) {
  // amount > 0 darkens toward black, < 0 lightens toward white.
  const channel = shift => {
    const value = (color >> shift) & 255;
    const next = amount > 0 ? value * (1 - amount) : value + (255 - value) * -amount;
    return Math.round(next) << shift;
  };
  return channel(16) | channel(8) | channel(0);
}

/** Where an outfit picture sits on her model at rest: the picture's eyes go onto her model's eyes.
 * `eyes`: her two eyes in the picture; `irises`: her two eyes on the model (both [{x, y}] left to right);
 * `fit`: {scale, x, y}, a nudge (x, y in eye spacings). Returns place(u, v): picture pixel → model point. */
export function outfitPlacement(eyes, irises, fit = {}) {
  const [e1, e2] = eyes.map(([x, y]) => ({x, y})), [m1, m2] = irises;
  const pictureSpan = Math.hypot(e2.x - e1.x, e2.y - e1.y), modelSpan = Math.hypot(m2.x - m1.x, m2.y - m1.y);
  if (pictureSpan < 1 || modelSpan <= 0) return null;
  const scale = modelSpan / pictureSpan * (fit.scale ?? 1);
  const angle = Math.atan2(m2.y - m1.y, m2.x - m1.x) - Math.atan2(e2.y - e1.y, e2.x - e1.x);
  const from = {x: (e1.x + e2.x) / 2, y: (e1.y + e2.y) / 2};
  const to = {x: (m1.x + m2.x) / 2 + (fit.x ?? 0) * modelSpan, y: (m1.y + m2.y) / 2 + (fit.y ?? 0) * modelSpan};
  return (u, v) => {
    const [x, y] = rotate((u - from.x) * scale, (v - from.y) * scale, angle);
    return {x: to.x + x, y: to.y + y};
  };
}

/** A grid over a picture, for drawing it as a mesh: texture coordinates, triangles, and each point's
 * pixel in the picture. */
export function pictureGrid(width, height, columns = 12, rows = 16) {
  const uvs = [], pixels = [], indices = [];
  for (let j = 0; j <= rows; j++)
    for (let i = 0; i <= columns; i++) {
      uvs.push(i / columns, j / rows);
      pixels.push([width * i / columns, height * j / rows]);
    }
  for (let j = 0; j < rows; j++)
    for (let i = 0; i < columns; i++) {
      const a = j * (columns + 1) + i, b = a + 1, c = a + columns + 1, d = c + 1;
      indices.push(a, b, c, b, d, c);
    }
  return {uvs: Float32Array.from(uvs), indices: Uint16Array.from(indices), pixels};
}
