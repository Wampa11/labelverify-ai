/**
 * Class-name merging helper for Tailwind / shadcn-style components.
 * Architectural responsibility: shared styling utility used by UI primitives.
 */
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Merge conditional class names with Tailwind-aware deduplication. */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
