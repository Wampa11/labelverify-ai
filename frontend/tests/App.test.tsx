/**
 * Tests for unified analyst workspace (Review Setup + Results).
 */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../src/App";
import * as api from "../src/services/api";
import type { SingleReviewVerificationResponse } from "../src/types/verification";

vi.mock("../src/services/api", async () => {
  const actual = await vi.importActual<typeof api>("../src/services/api");
  return {
    ...actual,
    analyzeLabel: vi.fn(),
    validateBatch: vi.fn(),
    createBatch: vi.fn(),
    fetchBatchStatus: vi.fn(),
    downloadSingleExcelReport: vi.fn(),
    downloadBatchExcelReport: vi.fn(),
    recordSiteAccess: vi.fn().mockResolvedValue(true),
  };
});

function mockSuccessResult(): SingleReviewVerificationResponse {
  return {
    analysis_id: "a1",
    verification_id: "v1",
    filename: "label.jpg",
    verification_mode: "label_only",
    application: null,
    display_image_base64:
      "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
    display_media_type: "image/jpeg",
    metadata_width_px: 640,
    metadata_height_px: 480,
    quality_status: "GOOD",
    quality_warnings: [],
    extraction: {
      analysis_id: "a1",
      selected_fields: {
        brand_name: {
          field_name: "brand_name",
          status: "FOUND",
          raw_text: "OLD TOM DISTILLERY",
          normalized_value: "OLD TOM DISTILLERY",
          normalized_numeric: null,
          normalized_unit: null,
          candidates: [],
          ocr_regions: [],
          extraction_method: "layout_heuristic",
          explanation: "ok",
          ai_fallback_hints: {},
        },
      },
      fast_pass: {
        profile: "fast",
        max_edge_px: 1600,
        provider_name: "tesseract",
        preprocessing_time_ms: 10,
        ocr_time_ms: 40,
        extraction_time_ms: 5,
        total_pass_time_ms: 55,
        ocr_text_preview: "OLD TOM",
        word_count: 10,
        image_width_px: 640,
        image_height_px: 480,
        fields: {},
        found_count: 1,
        uncertain_count: 0,
        not_found_count: 0,
      },
      enhanced_pass: null,
      retry: { triggered: false, reasons: [], performed: false },
      selection: {
        selected_profile: "fast",
        reason: "Only FAST pass available.",
        fast_score: 2,
        enhanced_score: null,
      },
      ocr_image_width_px: 640,
      ocr_image_height_px: 480,
      display_image_width_px: 640,
      display_image_height_px: 480,
      stage_timings_ms: {},
      processing_time_ms: 100,
      disclaimer: "Extraction only.",
    },
    verification: {
      verification_id: "v1",
      product_class: "distilled_spirits",
      verification_mode: "label_only",
      overall_status: "PASS",
      checks: [
        {
          check_name: "Brand Name",
          application_value: null,
          detected_label_value: "OLD TOM DISTILLERY",
          status: "PASS",
          explanation: "Recovered from the label image.",
          decision_method: "deterministic_rule",
          reason_code: "BRAND_MATCH",
        },
      ],
      pass_count: 1,
      review_count: 0,
      fail_count: 0,
      processing_time_ms: 120,
      ai_used: false,
      ai_degraded: false,
      degradation_notes: [],
      disclaimer: "Decision support only.",
    },
    processing_time_ms: 120,
    stage_timings_ms: {},
    disclaimer: "Decision support only.",
  };
}

describe("Analyst workspace", () => {
  beforeEach(() => {
    vi.mocked(api.analyzeLabel).mockReset();
    vi.mocked(api.downloadSingleExcelReport).mockReset();
    vi.mocked(api.recordSiteAccess).mockReset();
    vi.mocked(api.recordSiteAccess).mockResolvedValue(true);
  });

  it("shows Review Setup tiles and empty Results", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: /review setup/i })).toBeInTheDocument();
    expect(screen.getByText(/ready for review/i)).toBeInTheDocument();
    expect(screen.getByText(/select single label or batch review to begin/i)).toBeInTheDocument();
    expect(screen.getByText(/LabelVerify · Prototype Decision Support/i)).toBeInTheDocument();
    expect(screen.getByText(/^v0\.8\.0$/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^single review$/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /single label/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /batch review/i })).toBeInTheDocument();
    // J — header no longer has Workspace / How It Works nav
    const header = document.querySelector("header");
    expect(header).toBeTruthy();
    expect(within(header as HTMLElement).queryByRole("navigation")).not.toBeInTheDocument();
    expect(
      within(header as HTMLElement).queryByRole("button", { name: /^workspace$/i }),
    ).not.toBeInTheDocument();
    expect(
      within(header as HTMLElement).queryByRole("button", { name: /^how it works$/i }),
    ).not.toBeInTheDocument();
  });

  it("opens Single Label dialog and analyzes into Results", async () => {
    vi.mocked(api.analyzeLabel).mockResolvedValue(mockSuccessResult());
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: /single label/i }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /analyze single label/i })).toBeInTheDocument();

    const file = new File([new Uint8Array([1, 2, 3])], "label.jpg", { type: "image/jpeg" });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: /^analyze label$/i }));

    await waitFor(() => {
      expect(api.analyzeLabel).toHaveBeenCalledWith(file);
    });
    expect(await screen.findByText(/extracted label information/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /download excel report/i })).toBeInTheDocument();
  });

  it("opens Batch Review dialog", async () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: /batch review/i }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /process batch/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /cancel/i })).toBeInTheDocument();
  });

  it("Analyze another label clears results and opens a clean Single Label modal", async () => {
    vi.mocked(api.analyzeLabel).mockResolvedValue(mockSuccessResult());
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: /single label/i }));
    const file = new File([new Uint8Array([1, 2, 3])], "label.jpg", { type: "image/jpeg" });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: /^analyze label$/i }));
    expect(await screen.findByText(/extracted label information/i)).toBeInTheDocument();
    expect(screen.getByText(/OLD TOM DISTILLERY/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /analyze another label/i }));
    expect(screen.queryByText(/extracted label information/i)).not.toBeInTheDocument();
    expect(screen.getByText(/ready for review/i)).toBeInTheDocument();
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /analyze single label/i })).toBeInTheDocument();

    expect(screen.queryByAltText(/selected label/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/label\.jpg/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^analyze label$/i })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(screen.getByText(/ready for review/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /single label/i }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /analyze single label/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^analyze label$/i })).toBeDisabled();
  });

  it("How It Works rail control opens modal without clearing Results", async () => {
    vi.mocked(api.analyzeLabel).mockResolvedValue(mockSuccessResult());
    render(<App />);

    // K — initial site_access telemetry
    await waitFor(() => {
      expect(api.recordSiteAccess).toHaveBeenCalled();
    });

    // A–B — control in left rail, separate from review tiles
    const rail = screen.getByTestId("how-it-works-rail");
    expect(within(rail).getByText(/^information$/i)).toBeInTheDocument();
    expect(within(rail).getByRole("button", { name: /how it works/i })).toBeInTheDocument();
    expect(rail.className).toMatch(/border-t/);
    expect(screen.getByRole("button", { name: /single label/i }).className).toMatch(
      /lv-setup-tile/,
    );
    expect(within(rail).getByRole("button", { name: /how it works/i }).className).toMatch(
      /lv-setup-info/,
    );

    // Populate Results first (G)
    fireEvent.click(screen.getByRole("button", { name: /single label/i }));
    const file = new File([new Uint8Array([1, 2, 3])], "label.jpg", { type: "image/jpeg" });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: /^analyze label$/i }));
    expect(await screen.findByText(/extracted label information/i)).toBeInTheDocument();

    // C — open How It Works modal
    fireEvent.click(within(rail).getByRole("button", { name: /how it works/i }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("heading", { name: /how labelverify works/i })).toBeInTheDocument();

    // D–E — content principles
    const dialogText = dialog.textContent ?? "";
    expect(dialogText).toMatch(/not intended to make final regulatory determinations/i);
    expect(dialogText).toMatch(/prototype decision-support statuses/i);
    expect(dialogText).toMatch(/does not independently make the final compliance decision/i);
    expect(dialogText).toMatch(/AI recovers text evidence only/i);

    // G — results still present under the modal
    expect(screen.getByText(/extracted label information/i)).toBeInTheDocument();
    expect(screen.getByText(/OLD TOM DISTILLERY/i)).toBeInTheDocument();

    // F — close returns to workspace with results intact
    fireEvent.click(within(dialog).getByRole("button", { name: /^close$/i }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(screen.getByText(/extracted label information/i)).toBeInTheDocument();
    expect(screen.getByText(/OLD TOM DISTILLERY/i)).toBeInTheDocument();

    // H — Single Label still opens its modal
    fireEvent.click(screen.getByRole("button", { name: /single label/i }));
    expect(await screen.findByRole("heading", { name: /analyze single label/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    // I — Batch Review still opens its modal
    fireEvent.click(screen.getByRole("button", { name: /batch review/i }));
    expect(await screen.findByRole("heading", { name: /process batch/i })).toBeInTheDocument();
  });

  it("telemetry failure does not create a user-visible failure", async () => {
    vi.mocked(api.recordSiteAccess).mockResolvedValue(false);
    render(<App />);
    await waitFor(() => {
      expect(api.recordSiteAccess).toHaveBeenCalled();
    });
    expect(screen.getByText(/ready for review/i)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
