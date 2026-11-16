# Appearance of the plots

[← Documentation](../README.md#documentation)

The Appearance panel sets the style of the 2D plots. Open it on a plot with the palette button in the title bar of the plot's panel, or with `Appearance…` in the plot's right-click menu; the tabs at its top switch between the three plots. Its sections, those of the plot chosen:

- **Curves**: the line pattern, color and width; the points of a curve (excitons of the dispersion, bright excitons of a spectrum) are drawn in its color. `Apply to` chooses whether the changes apply to all the curves or to one of them (named after its exciton, Q-point or band); clicking a curve in a plot chooses it there. With all the curves, their colors can be:
  - one color for all (`Color`; with several colors in use, its swatch shows them as stripes);
  - a gradient (`Gradient`) from the first color (first curve) to the second (last curve), in that order, with their brightness and saturation;
  - a different color per curve (`Different color per curve`), from a set of distinct colors readable on light and dark backgrounds; this is the default for the absorption spectra, where each Q-point keeps its color as spectra are added and removed.

  Spectra added later take the width, pattern and symbols chosen for all, and the colors as chosen (the same color, their place in the gradient, or their Q-point's color). `Draw the lines` (on by default, for each plot) draws the lines of its curves: for the dispersion, the interpolated curves, or the points of each exciton joined when it is not interpolated; for the absorption, the spectra; for the band structure, the edges of the fill. Untick it for the points alone (in exported figures too).
- **Symbols** (dispersion and absorption): the shape and size of the points; `Different shape per curve` gives each curve a shape of its own, and `Shape` then reads `Different per curve`: choosing a shape gives it to all of them again. `Pattern` works the same way when the curves have different line patterns.
- **Axes**: the color and font of the title, axis labels and tick labels, the color and width of the axes, and the background. With `Same axes style for all plots`, the changes apply to the three plots.
- **Legend** (absorption): its text color and size, background (`None` for a transparent one), border and position.
- **Fill** (band structure): the color of the excitonic weights around the bands, and their scale (`Weight factor`).

The color and font buttons show the current value and open a dialog that previews the change on the plot as you pick: `OK` keeps it, `Cancel` restores the style as it was, each curve's included. The Appearance is kept between sessions and in session files.
