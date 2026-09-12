import { LIGHT_CORE_SIGMA, MIN_DUST_PIXELS, MIN_LIGHT_PIXELS } from "./lightSampling";

// Shared deformation keeps luminous arcs, stars and the rim on one living surface.
export const deformation = /* glsl */ `
  uniform float uTime;
  uniform float uEnergy;
  uniform float uWarmth;
  uniform float uBrightness;
  uniform float uAmplitude;
  uniform float uRestLight;
  // View-space direction keeps the resting highlight at the viewer's lower right.
  float restLighting(vec3 normal) {
    float direction = dot(normalize(normal), normalize(vec3(.65, -.76, 0.)));
    float focused = .42 + .83 * smoothstep(-.7, .9, direction);
    return mix(1., focused, uRestLight);
  }
  vec3 deform(vec3 p) {
    vec3 n = normalize(p);
    float wave = sin(n.x * 5.0 + uTime * .65) * sin(n.y * 4.0 - uTime * .48)
               + .5 * sin(n.z * 7.0 + n.x * 3.0 + uTime * .38);
    return p * (1.0 + wave * (.012 + uEnergy * .016 + uAmplitude * .022));
  }
  // Additive light on a transparent canvas: alpha has to follow the emitted
  // brightness. A constant 1. saturates alpha wherever anything draws at all,
  // turning dim areas into an opaque near-black patch over the page behind.
  vec4 emit(vec3 c) { return vec4(c, max(max(c.r, c.g), c.b)); }
  vec3 palette(float variation) {
    vec3 blue = mix(vec3(.025, .16, 1.), vec3(.1, .72, 1.), variation);
    blue = mix(blue, vec3(.57, .08, 1.), smoothstep(.88, 1., variation) * .85);
    vec3 orange = mix(vec3(1., .13, .008), vec3(1., .6, .12), variation);
    return mix(blue, orange, uWarmth);
  }
`;

export const pointVertex = /* glsl */ `
  ${deformation}
  attribute vec3 aCenter;
  attribute float aSize;
  attribute float aSeed;
  attribute float aStrength;
  uniform float uViewportHeight;
  varying float vLight;
  varying float vSeed;
  varying vec2 vLightUv;
  void main() {
    vec4 mv = modelViewMatrix * vec4(deform(aCenter), 1.);
    vSeed = aSeed;
    float pixelsPerUnit = uViewportHeight * .5 * projectionMatrix[1][1] / -mv.z;
    float minimum = aStrength < .1 ? ${MIN_DUST_PIXELS.toFixed(1)} : ${MIN_LIGHT_PIXELS.toFixed(1)};
    float wanted = aSize * pixelsPerUnit;
    float diameter = clamp(wanted, minimum, 84.);
    // Holding a distant light at a stable minimum size must not invent light.
    // Spreading it over a larger disc dims it by the area ratio, so thousands
    // of additive sprites keep summing to the exposure they would really have.
    float conservation = min(wanted / diameter, 1.);
    vLight = aStrength * conservation * conservation;
    mv.xy += position.xy * diameter / pixelsPerUnit;
    vLightUv = position.xy;
    gl_Position = projectionMatrix * mv;
  }
`;

// Move exterior lights along their existing closed orbit, not away from its line.
export const orbitPointVertex = /* glsl */ `
  uniform float uFlowTime;
  attribute float aOrbitIndex;
` + pointVertex.replace(
  "vec4 mv = modelViewMatrix * vec4(deform(aCenter), 1.);",
  /* glsl */ `
    float angle = atan(aCenter.y / .4, aCenter.x / (2.02 + aOrbitIndex * .095));
    angle += uFlowTime * (.24 + aOrbitIndex * .035);
    float radius = 1. + .025 * sin(angle * 5. + aOrbitIndex);
    vec3 center = vec3(cos(angle) * (2.02 + aOrbitIndex * .095), sin(angle) * .4, sin(angle) * 1.91) * radius;
    vec4 mv = modelViewMatrix * vec4(deform(center), 1.);
  `,
).replace(
  "vLight = aStrength * conservation * conservation;",
  "vLight = aStrength * conservation * conservation * 1.6;",
);

export const pointFragment = /* glsl */ `
  ${deformation}
  varying float vLight;
  varying float vSeed;
  varying vec2 vLightUv;
  float filteredGaussian(vec2 uv, float sigma) {
    vec2 variance = vec2(sigma * sigma);
    vec2 filtered = variance + fwidth(uv) * fwidth(uv) / 12.;
    return sqrt(variance.x * variance.y / (filtered.x * filtered.y))
         * exp(-.5 * dot(uv * uv, 1. / filtered));
  }
  void main() {
    vec2 uv = vLightUv;
    float r = length(uv);
    float core = filteredGaussian(uv, ${LIGHT_CORE_SIGMA});
    float glow = filteredGaussian(uv, .15) * .022;
    float edge = 1. - smoothstep(.34, .5, r);
    vec3 light = palette(vSeed) * glow * 1.5;
    light += mix(palette(vSeed), vec3(.88, .96, 1.), .65) * core * .28;
    gl_FragColor = emit(light * edge * vLight * uBrightness);
  }
`;

export const cometVertex = /* glsl */ `
  ${deformation}
  uniform float uFlowTime;
  uniform float uViewportHeight;
  attribute vec3 aCenter;
  attribute vec3 aEnd;
  attribute float aTrail;
  attribute float aDuration;
  attribute float aOffset;
  varying float vLight;
  varying float vSeed;
  varying vec2 vLightUv;
  void main() {
    float head = mod(uFlowTime * 2. / aDuration + aOffset * 1.35, 1.35);
    float progress = head - aTrail * .24;
    float visible = step(0., progress) * step(progress, 1.);
    vec3 p = normalize(mix(aCenter, aEnd, clamp(progress, 0., 1.))) * 1.8;
    vec4 mv = modelViewMatrix * vec4(deform(p), 1.);
    float fade = smoothstep(0., .035, progress) * (1. - smoothstep(.965, 1., progress));
    float headCore = 1. - smoothstep(0., .06, aTrail);
    vSeed = .72;
    float size = mix(.06, .20, pow(1. - aTrail, 3.));
    float pixelsPerUnit = uViewportHeight * .5 * projectionMatrix[1][1] / -mv.z;
    float wanted = size * pixelsPerUnit;
    float diameter = clamp(wanted, mix(${MIN_LIGHT_PIXELS.toFixed(1)}, ${MIN_DUST_PIXELS.toFixed(1)}, aTrail), 45.);
    float conservation = min(wanted / diameter, 1.);
    vLight = visible * fade * (headCore * 1.1 + pow(1. - aTrail, 2.) * .10) * conservation * conservation * 1.6;
    mv.xy += position.xy * diameter / pixelsPerUnit;
    vLightUv = position.xy;
    gl_Position = projectionMatrix * mv;
  }
`;

export const lineVertex = /* glsl */ `
  ${deformation}
  varying float vDepth;
  void main() {
    vec4 mv = modelViewMatrix * vec4(deform(position), 1.);
    vDepth = 1. - smoothstep(5.5, 9.5, -mv.z);
    gl_Position = projectionMatrix * mv;
  }
`;

export const lineFragment = /* glsl */ `
  ${deformation}
  varying float vDepth;
  void main() {
    // Fade rear connections more strongly so the network reads as depth.
    float light = (.014 + vDepth * .075) * (.70 + .30 * vDepth) * uBrightness * (1. + uAmplitude * .15);
    gl_FragColor = emit(palette(vDepth * .85) * light);
  }
`;

export const meshGlowVertex = /* glsl */ `
  ${deformation}
  uniform float uViewportHeight;
  uniform float uViewportAspect;
  attribute vec3 aCenter;
  attribute vec3 aEnd;
  varying float vAcross;
  varying float vDepth;
  void main() {
    vec4 start = modelViewMatrix * vec4(deform(aCenter), 1.);
    vec4 end = modelViewMatrix * vec4(deform(aEnd), 1.);
    vec4 a = projectionMatrix * start;
    vec4 b = projectionMatrix * end;
    vec2 aspect = vec2(uViewportAspect, 1.);
    vec2 direction = (b.xy / b.w - a.xy / a.w) * aspect;
    float segmentLength = length(direction);
    vec2 normal = vec2(-direction.y, direction.x) / max(segmentLength, .00001);
    vec4 p = mix(a, b, position.x + .5);
    p.xy += normal / aspect * position.y * 10. / max(uViewportHeight, 1.) * p.w;
    vAcross = position.y * 2.;
    vDepth = 1. - smoothstep(5.5, 9.5, -mix(start.z, end.z, position.x + .5));
    gl_Position = p;
  }
`;

export const meshGlowFragment = /* glsl */ `
  ${deformation}
  varying float vAcross;
  varying float vDepth;
  void main() {
    float soft = exp(-vAcross * vAcross * 5.) * (1. - smoothstep(.7, 1., abs(vAcross)));
    float light = soft * (.005 + .022 * vDepth) * .45 * uBrightness;
    gl_FragColor = emit(palette(.7) * light);
  }
`;

export const surfaceVertex = /* glsl */ `
  ${deformation}
  varying vec3 vNormal;
  varying vec3 vView;
  varying vec3 vPosition;
  void main() {
    vec3 p = deform(position);
    vec4 mv = modelViewMatrix * vec4(p, 1.);
    vPosition = p;
    vNormal = normalize(normalMatrix * normal);
    vView = normalize(-mv.xyz);
    gl_Position = projectionMatrix * mv;
  }
`;

// Soft inner light behind the network, keeping both sides of the mesh visible.
export const coreFragment = /* glsl */ `
  ${deformation}
  varying vec3 vNormal;
  varying vec3 vView;
  void main() {
    float facing = max(dot(normalize(vNormal), normalize(vView)), 0.);
    float opacity = .88 * smoothstep(.10, .65, facing);
    vec3 innerLight = palette(.55) * (.004 + .004 * pow(facing, 3.));
    gl_FragColor = vec4(innerLight * uBrightness * restLighting(vNormal), opacity);
  }
`;

export const surfaceFragment = /* glsl */ `
  ${deformation}
  varying vec3 vNormal;
  varying vec3 vView;
  varying vec3 vPosition;
  void main() {
    float facing = max(dot(normalize(vNormal), normalize(vView)), 0.);
    float grazing = 1. - facing;
    // Leave the front-facing core transparent. Fade into the luminous shell
    // smoothly, preserving the silhouette's peak brightness without a blue veil.
    float shell = smoothstep(.25, .72, grazing);
    float rim = pow(grazing, 6.);
    float thinRim = pow(grazing, 14.);
    // Broad, slowly advected filaments break up the solid ring without flashing.
    vec3 n = normalize(vPosition);
    float filament = sin(n.x * 19. + n.y * 11. + sin(n.z * 13.) * 2. + uTime * .10);
    float weave = sin(n.z * 27. - n.y * 17. + sin(n.x * 15.) + uTime * .07);
    float textureLight = .72 + .20 * filament + .08 * weave;
    vec3 color = palette(.72) * (rim * 1.15 + thinRim * 3.5) * shell * textureLight * 1.4;
    gl_FragColor = emit(color * uBrightness * (1. + uAmplitude * .35) * restLighting(vNormal));
  }
`;
