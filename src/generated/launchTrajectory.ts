/*
 * GENERATED FILE — do not edit by hand.
 *
 * Produced by scripts/gen_launch_assets.py from the physics solver in
 * native/trajectory/trajectory.c. Regenerate with:
 *
 *   uv run --project backend python scripts/gen_launch_assets.py
 *
 * Positions are normalised stage units: x and y both in [0, 1], y down.
 * `sx` and `sy` are separate so squash-and-stretch can be non-uniform.
 */

export interface LaunchFrame {
  /** Seconds since release. */
  t: number
  x: number
  y: number
  sx: number
  sy: number
  /** Degrees. */
  rotate: number
  opacity: number
}

export interface LaunchTrajectory {
  fps: number
  durationMs: number
  /** When the logo first touches down — the beat the tree reacts on. */
  landedAtMs: number
  bounces: number
  /** Stage width / height the solver assumed. */
  aspect: number
  /** The branch tip the logo departs from. */
  anchor: { x: number; y: number }
  /** Where it comes to rest. */
  rest: { x: number; y: number }
  frames: LaunchFrame[]
}

/** Grown from seed 20260929. */
export const LAUNCH_TRAJECTORY: LaunchTrajectory = {
  fps: 60,
  durationMs: 2650,
  landedAtMs: 851.4,
  bounces: 3,
  aspect: 1.6,
  anchor: { x: 0.29069, y: 0.237715 },
  rest: { x: 0.5, y: 0.62 },
  frames: [
    { t: 0, x: 0.29069, y: 0.23772, sx: 0.13793, sy: 0.1856, rotate: 0, opacity: 0 },
    { t: 0.0168, x: 0.29388, y: 0.23417, sx: 0.13853, sy: 0.1848, rotate: -2.508, opacity: 0.12 },
    { t: 0.0334, x: 0.29702, y: 0.23113, sx: 0.13929, sy: 0.18379, rotate: -4.964, opacity: 0.2386 },
    { t: 0.05, x: 0.30016, y: 0.22855, sx: 0.13997, sy: 0.1829, rotate: -7.397, opacity: 0.3571 },
    { t: 0.0668, x: 0.30333, y: 0.22639, sx: 0.14057, sy: 0.18212, rotate: -9.838, opacity: 0.4771 },
    { t: 0.0834, x: 0.30645, y: 0.22472, sx: 0.14105, sy: 0.18149, rotate: -12.227, opacity: 0.5957 },
    { t: 0.1, x: 0.30957, y: 0.22351, sx: 0.14143, sy: 0.18101, rotate: -14.594, opacity: 0.7143 },
    { t: 0.1168, x: 0.31273, y: 0.22273, sx: 0.14168, sy: 0.18069, rotate: -16.968, opacity: 0.8343 },
    { t: 0.1334, x: 0.31584, y: 0.22243, sx: 0.14179, sy: 0.18054, rotate: -19.292, opacity: 0.9529 },
    { t: 0.15, x: 0.31894, y: 0.22257, sx: 0.14178, sy: 0.18056, rotate: -21.596, opacity: 1 },
    { t: 0.1668, x: 0.32208, y: 0.22317, sx: 0.14163, sy: 0.18075, rotate: -23.905, opacity: 1 },
    { t: 0.1834, x: 0.32518, y: 0.22422, sx: 0.14136, sy: 0.1811, rotate: -26.167, opacity: 1 },
    { t: 0.2, x: 0.32827, y: 0.22571, sx: 0.14097, sy: 0.1816, rotate: -28.407, opacity: 1 },
    { t: 0.2168, x: 0.33139, y: 0.22768, sx: 0.14047, sy: 0.18225, rotate: -30.654, opacity: 1 },
    { t: 0.2334, x: 0.33447, y: 0.23007, sx: 0.13987, sy: 0.18302, rotate: -32.854, opacity: 1 },
    { t: 0.25, x: 0.33754, y: 0.23292, sx: 0.1392, sy: 0.18391, rotate: -35.034, opacity: 1 },
    { t: 0.2668, x: 0.34064, y: 0.23624, sx: 0.13845, sy: 0.18491, rotate: -37.22, opacity: 1 },
    { t: 0.2834, x: 0.3437, y: 0.23998, sx: 0.13793, sy: 0.1856, rotate: -39.36, opacity: 1 },
    { t: 0.3, x: 0.34676, y: 0.24415, sx: 0.13796, sy: 0.18565, rotate: -41.481, opacity: 1 },
    { t: 0.3168, x: 0.34984, y: 0.24883, sx: 0.1381, sy: 0.18583, rotate: -43.608, opacity: 1 },
    { t: 0.3334, x: 0.35288, y: 0.25389, sx: 0.13845, sy: 0.18629, rotate: -45.69, opacity: 1 },
    { t: 0.35, x: 0.35592, y: 0.25939, sx: 0.13914, sy: 0.18723, rotate: -47.753, opacity: 1 },
    { t: 0.3668, x: 0.35898, y: 0.2654, sx: 0.14039, sy: 0.18891, rotate: -49.822, opacity: 1 },
    { t: 0.3834, x: 0.362, y: 0.27178, sx: 0.14239, sy: 0.19161, rotate: -51.848, opacity: 1 },
    { t: 0.4, x: 0.36501, y: 0.27859, sx: 0.14542, sy: 0.19568, rotate: -53.855, opacity: 1 },
    { t: 0.4168, x: 0.36805, y: 0.28592, sx: 0.14984, sy: 0.20163, rotate: -55.868, opacity: 1 },
    { t: 0.4334, x: 0.37104, y: 0.29359, sx: 0.15588, sy: 0.20975, rotate: -57.839, opacity: 1 },
    { t: 0.45, x: 0.37403, y: 0.30169, sx: 0.16392, sy: 0.22058, rotate: -59.792, opacity: 1 },
    { t: 0.4668, x: 0.37704, y: 0.31032, sx: 0.17448, sy: 0.23479, rotate: -61.75, opacity: 1 },
    { t: 0.4834, x: 0.38, y: 0.31927, sx: 0.18767, sy: 0.25253, rotate: -63.667, opacity: 1 },
    { t: 0.5, x: 0.38296, y: 0.32865, sx: 0.20392, sy: 0.2744, rotate: -65.567, opacity: 1 },
    { t: 0.5168, x: 0.38594, y: 0.33855, sx: 0.2238, sy: 0.30114, rotate: -67.472, opacity: 1 },
    { t: 0.5334, x: 0.38887, y: 0.34876, sx: 0.24707, sy: 0.33246, rotate: -69.338, opacity: 1 },
    { t: 0.55, x: 0.39179, y: 0.35938, sx: 0.27411, sy: 0.36884, rotate: -71.186, opacity: 1 },
    { t: 0.5668, x: 0.39474, y: 0.37054, sx: 0.30537, sy: 0.41091, rotate: -73.039, opacity: 1 },
    { t: 0.5834, x: 0.39764, y: 0.38198, sx: 0.34006, sy: 0.45758, rotate: -74.854, opacity: 1 },
    { t: 0.6, x: 0.40052, y: 0.39382, sx: 0.37831, sy: 0.50906, rotate: -76.652, opacity: 1 },
    { t: 0.6168, x: 0.40343, y: 0.40621, sx: 0.4203, sy: 0.56556, rotate: -78.456, opacity: 1 },
    { t: 0.6334, x: 0.4063, y: 0.41885, sx: 0.46451, sy: 0.62505, rotate: -80.221, opacity: 1 },
    { t: 0.65, x: 0.40915, y: 0.43188, sx: 0.51073, sy: 0.68724, rotate: -81.97, opacity: 1 },
    { t: 0.6668, x: 0.41202, y: 0.44547, sx: 0.55869, sy: 0.75177, rotate: -83.725, opacity: 1 },
    { t: 0.6834, x: 0.41484, y: 0.45928, sx: 0.60624, sy: 0.81575, rotate: -85.442, opacity: 1 },
    { t: 0.7, x: 0.41765, y: 0.47347, sx: 0.6528, sy: 0.87841, rotate: -87.144, opacity: 1 },
    { t: 0.7168, x: 0.42048, y: 0.48823, sx: 0.69769, sy: 0.93881, rotate: -88.851, opacity: 1 },
    { t: 0.7334, x: 0.42326, y: 0.50318, sx: 0.73857, sy: 0.99382, rotate: -90.522, opacity: 1 },
    { t: 0.75, x: 0.42602, y: 0.51851, sx: 0.77479, sy: 1.04256, rotate: -92.178, opacity: 1 },
    { t: 0.7668, x: 0.42881, y: 0.53439, sx: 0.80562, sy: 1.08404, rotate: -93.838, opacity: 1 },
    { t: 0.7834, x: 0.43155, y: 0.55045, sx: 0.8295, sy: 1.11618, rotate: -95.464, opacity: 1 },
    { t: 0.8, x: 0.43427, y: 0.56688, sx: 0.84646, sy: 1.139, rotate: -97.075, opacity: 1 },
    { t: 0.8168, x: 0.43701, y: 0.58386, sx: 0.85679, sy: 1.15289, rotate: -98.69, opacity: 1 },
    { t: 0.8334, x: 0.4397, y: 0.601, sx: 0.86124, sy: 1.15889, rotate: -100.271, opacity: 1 },
    { t: 0.85, x: 0.44237, y: 0.61848, sx: 0.86207, sy: 1.16, rotate: -101.839, opacity: 1 },
    { t: 0.8668, x: 0.44414, y: 0.61437, sx: 1.08558, sy: 0.92112, rotate: -102.575, opacity: 1 },
    { t: 0.8834, x: 0.44579, y: 0.60866, sx: 1.0222, sy: 0.97788, rotate: -103.221, opacity: 1 },
    { t: 0.9, x: 0.44743, y: 0.60341, sx: 0.97064, sy: 1.02893, rotate: -103.862, opacity: 1 },
    { t: 0.9168, x: 0.44909, y: 0.59857, sx: 0.92789, sy: 1.07479, rotate: -104.504, opacity: 1 },
    { t: 0.9334, x: 0.45073, y: 0.59424, sx: 0.89637, sy: 1.11044, rotate: -105.132, opacity: 1 },
    { t: 0.95, x: 0.45237, y: 0.59038, sx: 0.87521, sy: 1.13467, rotate: -105.755, opacity: 1 },
    { t: 0.9668, x: 0.45402, y: 0.58693, sx: 0.86323, sy: 1.14745, rotate: -106.38, opacity: 1 },
    { t: 0.9834, x: 0.45565, y: 0.58398, sx: 0.85928, sy: 1.14967, rotate: -106.992, opacity: 1 },
    { t: 1, x: 0.45728, y: 0.58148, sx: 0.86166, sy: 1.14357, rotate: -107.598, opacity: 1 },
    { t: 1.0168, x: 0.45892, y: 0.57942, sx: 0.86887, sy: 1.1314, rotate: -108.206, opacity: 1 },
    { t: 1.0334, x: 0.46055, y: 0.57783, sx: 0.87912, sy: 1.11601, rotate: -108.801, opacity: 1 },
    { t: 1.05, x: 0.46217, y: 0.5767, sx: 0.89084, sy: 1.09969, rotate: -109.39, opacity: 1 },
    { t: 1.0668, x: 0.46381, y: 0.57601, sx: 0.90264, sy: 1.0843, rotate: -109.982, opacity: 1 },
    { t: 1.0834, x: 0.46543, y: 0.57579, sx: 0.91289, sy: 1.07179, rotate: -110.561, opacity: 1 },
    { t: 1.1, x: 0.46705, y: 0.57601, sx: 0.92076, sy: 1.06296, rotate: -111.134, opacity: 1 },
    { t: 1.1168, x: 0.46869, y: 0.5767, sx: 0.92572, sy: 1.05825, rotate: -111.709, opacity: 1 },
    { t: 1.1334, x: 0.47031, y: 0.57783, sx: 0.92754, sy: 1.05775, rotate: -112.273, opacity: 1 },
    { t: 1.15, x: 0.47192, y: 0.57941, sx: 0.92648, sy: 1.06104, rotate: -112.831, opacity: 1 },
    { t: 1.1668, x: 0.47356, y: 0.58146, sx: 0.92289, sy: 1.06767, rotate: -113.39, opacity: 1 },
    { t: 1.1834, x: 0.47517, y: 0.58394, sx: 0.91735, sy: 1.07686, rotate: -113.938, opacity: 1 },
    { t: 1.2, x: 0.47678, y: 0.58687, sx: 0.91037, sy: 1.08798, rotate: -114.481, opacity: 1 },
    { t: 1.2168, x: 0.4784, y: 0.59029, sx: 0.90229, sy: 1.10056, rotate: -115.026, opacity: 1 },
    { t: 1.2334, x: 0.48001, y: 0.59412, sx: 0.8937, sy: 1.11369, rotate: -115.559, opacity: 1 },
    { t: 1.25, x: 0.48161, y: 0.59839, sx: 0.88483, sy: 1.12702, rotate: -116.087, opacity: 1 },
    { t: 1.2668, x: 0.48323, y: 0.60316, sx: 0.87578, sy: 1.1403, rotate: -116.617, opacity: 1 },
    { t: 1.2834, x: 0.48483, y: 0.60832, sx: 0.86694, sy: 1.15295, rotate: -117.135, opacity: 1 },
    { t: 1.3, x: 0.48642, y: 0.61392, sx: 0.86122, sy: 1.16106, rotate: -117.649, opacity: 1 },
    { t: 1.3168, x: 0.48803, y: 0.62, sx: 1.02253, sy: 0.97797, rotate: -118.161, opacity: 1 },
    { t: 1.3334, x: 0.48901, y: 0.61798, sx: 1.01426, sy: 0.98594, rotate: -118.373, opacity: 1 },
    { t: 1.35, x: 0.49, y: 0.6164, sx: 1.00246, sy: 0.99753, rotate: -118.583, opacity: 1 },
    { t: 1.3668, x: 0.49099, y: 0.61527, sx: 0.98929, sy: 1.01079, rotate: -118.793, opacity: 1 },
    { t: 1.3834, x: 0.49197, y: 0.61461, sx: 0.97631, sy: 1.02421, rotate: -119, opacity: 1 },
    { t: 1.4, x: 0.49295, y: 0.61439, sx: 0.96376, sy: 1.03755, rotate: -119.204, opacity: 1 },
    { t: 1.4168, x: 0.49395, y: 0.61464, sx: 0.95168, sy: 1.05073, rotate: -119.409, opacity: 1 },
    { t: 1.4334, x: 0.49493, y: 0.61533, sx: 0.9407, sy: 1.06301, rotate: -119.609, opacity: 1 },
    { t: 1.45, x: 0.49591, y: 0.61647, sx: 0.93106, sy: 1.07403, rotate: -119.808, opacity: 1 },
    { t: 1.4668, x: 0.4969, y: 0.61809, sx: 0.92281, sy: 1.08364, rotate: -120.007, opacity: 1 },
    { t: 1.4834, x: 0.49786, y: 0.61996, sx: 0.99969, sy: 1.00031, rotate: -120.196, opacity: 1 },
    { t: 1.5, x: 0.49847, y: 0.6194, sx: 0.9995, sy: 1.0005, rotate: -120.277, opacity: 1 },
    { t: 1.5168, x: 0.49908, y: 0.6193, sx: 0.99394, sy: 1.00609, rotate: -120.358, opacity: 1 },
    { t: 1.5334, x: 0.49969, y: 0.61964, sx: 0.98358, sy: 1.0167, rotate: -120.438, opacity: 1 },
    { t: 1.55, x: 0.5, y: 0.62, sx: 1.02834, sy: 0.97244, rotate: -120.045, opacity: 1 },
    { t: 1.5668, x: 0.5, y: 0.62, sx: 1.02205, sy: 0.97843, rotate: -116.765, opacity: 1 },
    { t: 1.5834, x: 0.5, y: 0.62, sx: 1.01534, sy: 0.98489, rotate: -111.268, opacity: 1 },
    { t: 1.6, x: 0.5, y: 0.62, sx: 1.00896, sy: 0.99112, rotate: -104.368, opacity: 1 },
    { t: 1.6168, x: 0.5, y: 0.62, sx: 1.00336, sy: 0.99665, rotate: -96.59, opacity: 1 },
    { t: 1.6334, x: 0.5, y: 0.62, sx: 0.99898, sy: 1.00103, rotate: -88.574, opacity: 1 },
    { t: 1.65, x: 0.5, y: 0.62, sx: 0.99585, sy: 1.00417, rotate: -80.554, opacity: 1 },
    { t: 1.6668, x: 0.5, y: 0.62, sx: 0.99392, sy: 1.00612, rotate: -72.66, opacity: 1 },
    { t: 1.6834, x: 0.5, y: 0.62, sx: 0.99309, sy: 1.00696, rotate: -65.232, opacity: 1 },
    { t: 1.7, x: 0.5, y: 0.62, sx: 0.99313, sy: 1.00691, rotate: -58.266, opacity: 1 },
    { t: 1.7168, x: 0.5, y: 0.62, sx: 0.99383, sy: 1.00621, rotate: -51.739, opacity: 1 },
    { t: 1.7334, x: 0.5, y: 0.62, sx: 0.99493, sy: 1.0051, rotate: -45.83, opacity: 1 },
    { t: 1.75, x: 0.5, y: 0.62, sx: 0.99623, sy: 1.00379, rotate: -40.456, opacity: 1 },
    { t: 1.7668, x: 0.5, y: 0.62, sx: 0.99757, sy: 1.00244, rotate: -35.547, opacity: 1 },
    { t: 1.7834, x: 0.5, y: 0.62, sx: 0.99879, sy: 1.00121, rotate: -31.197, opacity: 1 },
    { t: 1.8, x: 0.5, y: 0.62, sx: 0.99981, sy: 1.00019, rotate: -27.311, opacity: 1 },
    { t: 1.8168, x: 0.5, y: 0.62, sx: 1.00059, sy: 0.99941, rotate: -23.816, opacity: 1 },
    { t: 1.8334, x: 0.5, y: 0.62, sx: 1.00111, sy: 0.99889, rotate: -20.76, opacity: 1 },
    { t: 1.85, x: 0.5, y: 0.62, sx: 1.00139, sy: 0.99861, rotate: -18.063, opacity: 1 },
    { t: 1.8668, x: 0.5, y: 0.62, sx: 1.00146, sy: 0.99854, rotate: -15.662, opacity: 1 },
    { t: 1.8834, x: 0.5, y: 0.62, sx: 1.00138, sy: 0.99863, rotate: -13.582, opacity: 1 },
    { t: 1.9, x: 0.5, y: 0.62, sx: 1.00118, sy: 0.99882, rotate: -11.761, opacity: 1 },
    { t: 1.9168, x: 0.5, y: 0.62, sx: 1.00092, sy: 0.99908, rotate: -10.153, opacity: 1 },
    { t: 1.9334, x: 0.5, y: 0.62, sx: 1.00064, sy: 0.99936, rotate: -8.769, opacity: 1 },
    { t: 1.95, x: 0.5, y: 0.62, sx: 1.00037, sy: 0.99963, rotate: -7.565, opacity: 1 },
    { t: 1.9668, x: 0.5, y: 0.62, sx: 1.00013, sy: 0.99987, rotate: -6.507, opacity: 1 },
    { t: 1.9834, x: 0.5, y: 0.62, sx: 0.99995, sy: 1.00005, rotate: -5.602, opacity: 1 },
    { t: 2, x: 0.5, y: 0.62, sx: 0.99981, sy: 1.00019, rotate: -4.818, opacity: 1 },
    { t: 2.0168, x: 0.5, y: 0.62, sx: 0.99973, sy: 1.00027, rotate: -4.132, opacity: 1 },
    { t: 2.0334, x: 0.5, y: 0.62, sx: 0.9997, sy: 1.0003, rotate: -3.548, opacity: 1 },
    { t: 2.05, x: 0.5, y: 0.62, sx: 0.9997, sy: 1.0003, rotate: -3.044, opacity: 1 },
    { t: 2.0668, x: 0.5, y: 0.62, sx: 0.99973, sy: 1.00027, rotate: -2.604, opacity: 1 },
    { t: 2.0834, x: 0.5, y: 0.62, sx: 0.99978, sy: 1.00022, rotate: -2.231, opacity: 1 },
    { t: 2.1, x: 0.5, y: 0.62, sx: 0.99984, sy: 1.00016, rotate: -1.91, opacity: 1 },
    { t: 2.1168, x: 0.5, y: 0.62, sx: 0.9999, sy: 1.0001, rotate: -1.631, opacity: 1 },
    { t: 2.1334, x: 0.5, y: 0.62, sx: 0.99995, sy: 1.00005, rotate: -1.394, opacity: 1 },
    { t: 2.15, x: 0.5, y: 0.62, sx: 0.99999, sy: 1.00001, rotate: -1.192, opacity: 1 },
    { t: 2.1668, x: 0.5, y: 0.62, sx: 1.00003, sy: 0.99997, rotate: -1.016, opacity: 1 },
    { t: 2.1834, x: 0.5, y: 0.62, sx: 1.00005, sy: 0.99995, rotate: -0.867, opacity: 1 },
    { t: 2.2, x: 0.5, y: 0.62, sx: 1.00006, sy: 0.99994, rotate: -0.74, opacity: 1 },
    { t: 2.2168, x: 0.5, y: 0.62, sx: 1.00006, sy: 0.99994, rotate: -0.63, opacity: 1 },
    { t: 2.2334, x: 0.5, y: 0.62, sx: 1.00006, sy: 0.99994, rotate: -0.537, opacity: 1 },
    { t: 2.25, x: 0.5, y: 0.62, sx: 1.00005, sy: 0.99995, rotate: -0.457, opacity: 1 },
    { t: 2.2668, x: 0.5, y: 0.62, sx: 1.00004, sy: 0.99996, rotate: -0.389, opacity: 1 },
    { t: 2.2834, x: 0.5, y: 0.62, sx: 1.00003, sy: 0.99997, rotate: -0.331, opacity: 1 },
    { t: 2.3, x: 0.5, y: 0.62, sx: 1.00002, sy: 0.99998, rotate: -0.282, opacity: 1 },
    { t: 2.3168, x: 0.5, y: 0.62, sx: 1.00001, sy: 0.99999, rotate: -0.239, opacity: 1 },
    { t: 2.3334, x: 0.5, y: 0.62, sx: 1, sy: 1, rotate: -0.203, opacity: 1 },
    { t: 2.35, x: 0.5, y: 0.62, sx: 0.99999, sy: 1.00001, rotate: -0.173, opacity: 1 },
    { t: 2.3668, x: 0.5, y: 0.62, sx: 0.99999, sy: 1.00001, rotate: -0.147, opacity: 1 },
    { t: 2.3834, x: 0.5, y: 0.62, sx: 0.99999, sy: 1.00001, rotate: -0.125, opacity: 1 },
    { t: 2.4, x: 0.5, y: 0.62, sx: 0.99999, sy: 1.00001, rotate: -0.106, opacity: 1 },
    { t: 2.4168, x: 0.5, y: 0.62, sx: 0.99999, sy: 1.00001, rotate: -0.09, opacity: 1 },
    { t: 2.4334, x: 0.5, y: 0.62, sx: 0.99999, sy: 1.00001, rotate: -0.076, opacity: 1 },
    { t: 2.45, x: 0.5, y: 0.62, sx: 0.99999, sy: 1.00001, rotate: -0.065, opacity: 1 },
    { t: 2.4668, x: 0.5, y: 0.62, sx: 1, sy: 1, rotate: -0.055, opacity: 1 },
    { t: 2.4834, x: 0.5, y: 0.62, sx: 1, sy: 1, rotate: 0, opacity: 1 },
    { t: 2.5, x: 0.5, y: 0.62, sx: 1, sy: 1, rotate: 0, opacity: 1 },
    { t: 2.5168, x: 0.5, y: 0.62, sx: 1, sy: 1, rotate: 0, opacity: 1 },
    { t: 2.5334, x: 0.5, y: 0.62, sx: 1, sy: 1, rotate: 0, opacity: 1 },
    { t: 2.55, x: 0.5, y: 0.62, sx: 1, sy: 1, rotate: 0, opacity: 1 },
    { t: 2.5668, x: 0.5, y: 0.62, sx: 1, sy: 1, rotate: 0, opacity: 1 },
    { t: 2.5834, x: 0.5, y: 0.62, sx: 1, sy: 1, rotate: 0, opacity: 1 },
    { t: 2.6, x: 0.5, y: 0.62, sx: 1, sy: 1, rotate: 0, opacity: 1 },
    { t: 2.6168, x: 0.5, y: 0.62, sx: 1, sy: 1, rotate: 0, opacity: 1 },
    { t: 2.6334, x: 0.5, y: 0.62, sx: 1, sy: 1, rotate: 0, opacity: 1 },
    { t: 2.65, x: 0.5, y: 0.62, sx: 1, sy: 1, rotate: 0, opacity: 1 },
  ],
}
