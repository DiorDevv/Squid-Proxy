import '@testing-library/jest-dom/vitest'

// jsdom doesn't implement the Pointer Events / scrollIntoView APIs Radix UI
// primitives (Select, Dropdown, etc.) rely on for open/close and keyboard
// navigation -- without these no-op polyfills, userEvent interactions with
// any Radix-based component throw "X is not a function" instead of testing
// the actual behavior.
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false
}
if (!Element.prototype.setPointerCapture) {
  Element.prototype.setPointerCapture = () => {}
}
if (!Element.prototype.releasePointerCapture) {
  Element.prototype.releasePointerCapture = () => {}
}
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {}
}
