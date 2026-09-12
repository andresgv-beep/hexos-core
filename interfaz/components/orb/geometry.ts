import { BufferGeometry, Float32BufferAttribute, InstancedBufferAttribute, InstancedBufferGeometry } from "three";

/** Camera-facing quads keep exact subpixel centers. GL_POINTS can snap their
 * rasterized centers/diameters as a light moves, which looks like blinking.
 */
function lightQuads(source: BufferGeometry) {
  const geometry = new InstancedBufferGeometry();
  geometry.setAttribute("position", new Float32BufferAttribute([
    -.5, -.5, 0, .5, -.5, 0, .5, .5, 0,
    -.5, -.5, 0, .5, .5, 0, -.5, .5, 0,
  ], 3));
  for (const [name, attribute] of Object.entries(source.attributes)) {
    geometry.setAttribute(name === "position" ? "aCenter" : name,
      new InstancedBufferAttribute(attribute.array, attribute.itemSize));
  }
  geometry.instanceCount = source.getAttribute("position").count;
  source.dispose();
  return geometry;
}

/** One camera-facing ribbon per segment, for a soft local glow. */
export function createMeshGlow(lines: BufferGeometry) {
  const vertices = lines.getAttribute("position");
  const starts: number[] = [], ends: number[] = [];
  for (let i = 0; i < vertices.count; i += 2) {
    starts.push(vertices.getX(i), vertices.getY(i), vertices.getZ(i));
    ends.push(vertices.getX(i + 1), vertices.getY(i + 1), vertices.getZ(i + 1));
  }
  const source = new BufferGeometry();
  source.setAttribute("position", new Float32BufferAttribute(starts, 3));
  source.setAttribute("aEnd", new Float32BufferAttribute(ends, 3));
  return lightQuads(source);
}

// Seeded geometry is generated once, then deformed on the GPU.
export function createOrbGeometry(count = 4200) {
  let seed = 731;
  function random() { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296; }
  const positions: number[] = [], sizes: number[] = [], seeds: number[] = [];
  const strengths: number[] = [];
  const anchors: number[][] = [];
  const anchorCount = 800;
  for (let i = 0; i < count; i++) {
    const y = 1 - 2 * random(), theta = random() * Math.PI * 2;
    const r = Math.sqrt(1 - y * y);
    const radius = i < anchorCount ? 1.8 : 1.8 * (.94 + random() * .08);
    const p = [Math.cos(theta) * r * radius, y * radius, Math.sin(theta) * r * radius];
    positions.push(...p);
    const star = random();
    // Mostly fine nodes, with only a few larger accents. The pixel filter still
    // stabilizes small cores without inflating their total light output.
    sizes.push(i < anchorCount ? .12 + Math.pow(star, 9) * .22 : .032 + star * .014);
    strengths.push(i < anchorCount ? .24 + star * .18 : .075);
    seeds.push(star);
    if (i < anchorCount) anchors.push(p);
  }
  const edges: number[] = [];
  const routes: [number[], number[]][] = [];
  for (let i = 0; i < anchors.length; i++) {
    const a = anchors[i];
    const neighbors: { point: number[]; distance: number }[] = [];
    for (let j = i + 1; j < anchors.length; j++) {
      const b = anchors[j];
      const d2 = (a[0]-b[0])**2 + (a[1]-b[1])**2 + (a[2]-b[2])**2;
      if (d2 > .035 && d2 < .32) neighbors.push({ point: b, distance: d2 });
    }
    // Prefer short local connections over the first random candidates.
    neighbors.sort((left, right) => left.distance - right.distance);
    for (const { point: b } of neighbors.slice(0, 3)) {
        routes.push([a, b]);
        let previous = a;
        for (let step = 1; step <= 8; step++) {
          const t = step / 8;
          const p = a.map((coordinate, axis) => coordinate * (1 - t) + b[axis] * t);
          const radius = Math.hypot(...p);
          const next = p.map(coordinate => coordinate / radius * 1.8);
          edges.push(...previous, ...next);
          previous = next;
        }
    }
  }
  const points = new BufferGeometry();
  points.setAttribute("position", new Float32BufferAttribute(positions, 3));
  points.setAttribute("aSize", new Float32BufferAttribute(sizes, 1));
  points.setAttribute("aSeed", new Float32BufferAttribute(seeds, 1));
  points.setAttribute("aStrength", new Float32BufferAttribute(strengths, 1));
  const lines = new BufferGeometry();
  lines.setAttribute("position", new Float32BufferAttribute(edges, 3));
  return { points: lightQuads(points), lines, comets: createComets(routes) };
}

function createComets(routes: [number[], number[]][]) {
  const positions: number[] = [], ends: number[] = [], trails: number[] = [];
  const durations: number[] = [], offsets: number[] = [];
  const cometCount = Math.min(16, routes.length);
  for (let i = 0; i < cometCount; i++) {
    const [start, end] = routes[Math.floor((i + .37) * routes.length / cometCount)];
    for (let sample = 0; sample < 36; sample++) {
      positions.push(...start); ends.push(...end); trails.push(sample / 35);
      durations.push(10 + i % 7); offsets.push((i * .61803398875) % 1);
    }
  }
  const comets = new BufferGeometry();
  comets.setAttribute("position", new Float32BufferAttribute(positions, 3));
  comets.setAttribute("aEnd", new Float32BufferAttribute(ends, 3));
  comets.setAttribute("aTrail", new Float32BufferAttribute(trails, 1));
  comets.setAttribute("aDuration", new Float32BufferAttribute(durations, 1));
  comets.setAttribute("aOffset", new Float32BufferAttribute(offsets, 1));
  return lightQuads(comets);
}

export function createOrbitGeometry(index: number) {
  const positions: number[] = [], sizes: number[] = [], seeds: number[] = [];
  const strengths: number[] = [];
  const trace: number[] = [];
  for (let i = 0; i <= 760; i++) {
    const t = i / 760 * Math.PI * 2;
    const radius = 1 + .025 * Math.sin(t * 5 + index);
    const p = [Math.cos(t) * (2.02 + index * .095) * radius, Math.sin(t) * .4, Math.sin(t) * 1.91 * radius];
    trace.push(...p);
    if (i < 760) {
      positions.push(...p);
      sizes.push(i % 127 === 0 ? .32 : .022);
      strengths.push(i % 127 === 0 ? .5 : .035);
      seeds.push(i % 127 === 0 ? .83 : .35);
    }
  }
  const points = new BufferGeometry();
  points.setAttribute("position", new Float32BufferAttribute(positions, 3));
  points.setAttribute("aSize", new Float32BufferAttribute(sizes, 1));
  points.setAttribute("aSeed", new Float32BufferAttribute(seeds, 1));
  points.setAttribute("aStrength", new Float32BufferAttribute(strengths, 1));
  points.setAttribute("aOrbitIndex", new Float32BufferAttribute(new Float32Array(strengths.length).fill(index), 1));
  const line = new BufferGeometry();
  line.setAttribute("position", new Float32BufferAttribute(trace, 3));
  return { points: lightQuads(points), line };
}
