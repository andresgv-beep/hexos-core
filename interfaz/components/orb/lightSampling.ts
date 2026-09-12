// Physical-pixel limits: the luminous core must cover more than a single pixel
// at every distance, so a light never flickers as it crosses pixel boundaries.
//
// What matters for that stability is the core's sigma *in pixels*
// (MIN_LIGHT_PIXELS * LIGHT_CORE_SIGMA), not the quad's size. Keeping that
// product constant lets the quad stay small, which is what keeps additive
// overdraw — and therefore the whole image's exposure — under control.
export const LIGHT_CORE_SIGMA = .05;
export const MIN_LIGHT_PIXELS = 28;
export const MIN_DUST_PIXELS = 3.5;
