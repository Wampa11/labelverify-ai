/**
 * How LabelVerify Works — evaluator-facing explainer content.
 * Architectural responsibility: document prototype workflow without inventing capabilities.
 */
import type { ReactNode } from "react";

/** Institutional explainer body (used inside HowItWorksModal). */
export function HowItWorksContent() {
  return (
    <div className="space-y-6 text-foreground">
      <section className="space-y-3">
        <p className="text-sm leading-relaxed text-foreground">
          LabelVerify is a prototype decision-support tool designed to assist alcohol
          label compliance review. It automates selected high-volume verification checks
          and flags uncertain results for human review. It is{" "}
          <strong className="font-semibold">not</strong> intended to make final
          regulatory determinations.
        </p>
      </section>

      <Section title="1. Upload">
        <p>
          Analysts start from the Review Setup workspace. <strong>Single Label</strong>{" "}
          review analyzes one distilled spirits label image. <strong>Batch Review</strong>{" "}
          processes multiple labels from a CSV manifest plus matching images.
        </p>
        <p>
          Supported prototype uploads are common label image formats (JPEG, PNG, WebP).
          Images are analyzed for verification and are not used as a permanent document
          archive in this prototype.
        </p>
      </Section>

      <Section title="2. Image Analysis">
        <p>
          Each upload is validated and prepared for reading. Optical character recognition
          (OCR) recovers text from the label image. Image quality is assessed with
          engineering heuristics; imperfect images may trigger additional evidence-recovery
          steps when needed.
        </p>
      </Section>

      <Section title="3. Structured Field Extraction">
        <p>
          The prototype extracts and evaluates selected fields commonly needed in distilled
          spirits label review:
        </p>
        <ul className="list-disc space-y-1 pl-5">
          <li>Brand Name</li>
          <li>Class / Type</li>
          <li>Alcohol Content</li>
          <li>Net Contents</li>
          <li>Government Health Warning</li>
        </ul>
        <p>
          Current regulatory prototype scope is <strong>distilled spirits</strong> only.
        </p>
      </Section>

      <Section title="4. Progressive Evidence Recovery">
        <p>
          LabelVerify starts with fast local processing. When evidence is uncertain, it can
          selectively use additional OCR techniques on relevant regions of the label.
        </p>
        <p>
          When configured and necessary, AI-assisted visual analysis may recover evidence
          that local OCR could not reliably read. AI recovers text evidence only — it does{" "}
          <strong>not</strong> independently make the final compliance decision.
        </p>
      </Section>

      <Section title="5. Deterministic Verification">
        <p>
          Defined rules evaluate recovered evidence. Normalization handles benign differences
          such as capitalization where appropriate. Clear material mismatches can result in
          FAIL. Uncertain or incomplete evidence becomes REVIEW rather than an automatic
          failure.
        </p>
      </Section>

      <Section title="6. PASS / REVIEW / FAIL">
        <dl className="space-y-3">
          <div>
            <dt className="font-semibold text-navy">PASS</dt>
            <dd>
              The selected automated checks were satisfied by sufficiently reliable evidence.
            </dd>
          </div>
          <div>
            <dt className="font-semibold text-navy">REVIEW</dt>
            <dd>
              One or more checks require human judgment or could not be established with
              sufficient confidence.
            </dd>
          </div>
          <div>
            <dt className="font-semibold text-navy">FAIL</dt>
            <dd>
              A sufficiently reliable, material mismatch was detected for an automated check.
            </dd>
          </div>
        </dl>
        <p className="mt-3">
          These are prototype decision-support statuses, not final TTB regulatory
          determinations.
        </p>
      </Section>

      <Section title="7. Human Review">
        <p>
          Uncertainty is intentionally surfaced rather than hidden. For example, small or
          low-contrast government warning text may be visibly present on a label but not
          reliably machine-readable, resulting in REVIEW so a compliance agent can inspect
          the image.
        </p>
      </Section>

      <Section title="8. Privacy / Prototype Data Handling">
        <ul className="list-disc space-y-1 pl-5">
          <li>Standalone prototype — no direct COLA system integration.</li>
          <li>
            No database is used to permanently store uploaded label images in the current
            implementation.
          </li>
          <li>
            Operational audit logs intentionally exclude label content, extracted text, and
            image payloads.
          </li>
          <li>External AI assistance is optional and configurable (off by default).</li>
        </ul>
        <p>
          This prototype does not claim FedRAMP authorization, federal production compliance
          certification, or formal retention-policy compliance.
        </p>
      </Section>

      <Section title="9. Performance">
        <p>
          Routine reviews prioritize fast local processing, with approximately five seconds
          as the stakeholder usability target. Difficult images may require additional
          evidence-recovery stages and therefore take longer. Processing time is not
          guaranteed.
        </p>
      </Section>

      <Section title="10. Prototype Scope / Limitations">
        <ul className="list-disc space-y-1 pl-5">
          <li>Regulatory prototype scope: distilled spirits</li>
          <li>Selected automated checks only</li>
          <li>Not a replacement for compliance-agent judgment</li>
          <li>Not a final regulatory determination</li>
          <li>
            Formatting and physical requirements that cannot be reliably established from an
            uploaded image (for example bold type or type size) may require human review
          </li>
        </ul>
      </Section>

      <details className="border border-border bg-muted/40 px-4 py-3 text-sm">
        <summary className="cursor-pointer font-semibold text-navy">
          Conceptual pipeline (technical detail)
        </summary>
        <ol className="mt-3 list-decimal space-y-1 pl-5 text-muted-foreground">
          <li>Upload</li>
          <li>Image Validation</li>
          <li>Local OCR</li>
          <li>Structured Extraction</li>
          <li>Selective Evidence Recovery</li>
          <li>Deterministic Verification</li>
          <li>PASS / REVIEW / FAIL</li>
          <li>Human Review when needed</li>
        </ol>
      </details>
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-2">
      <h2 className="font-display text-base font-semibold text-navy sm:text-lg">{title}</h2>
      <div className="space-y-2 text-sm leading-relaxed text-foreground">{children}</div>
    </section>
  );
}
