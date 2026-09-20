/**
 * Vitest setup for DOM matchers and browser API stubs.
 * Architectural responsibility: shared test environment bootstrap.
 */
import "@testing-library/jest-dom/vitest";

if (typeof URL.createObjectURL !== "function") {
  URL.createObjectURL = () => "blob:test-preview";
}
if (typeof URL.revokeObjectURL !== "function") {
  URL.revokeObjectURL = () => undefined;
}
