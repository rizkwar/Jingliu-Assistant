// Bound supersampling independently of the desktop window's size.
export function drawingSize(width, height, deviceRatio, hd) {
  const native = Number.isFinite(deviceRatio) && deviceRatio > 0 ? deviceRatio : 1;
  const requested = hd ? Math.min(native * 1.5, 3) : Math.min(native, 2);
  const ratio = Math.min(requested, 2048 / Math.max(width, height, 1));
  return [Math.max(1, Math.round(width * ratio)), Math.max(1, Math.round(height * ratio))];
}
