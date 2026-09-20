/**
 * How It Works informational modal.
 * Architectural responsibility: overlay explainer without resetting workspace state.
 */
import { Modal } from "../common/Modal";
import { HowItWorksContent } from "./HowItWorksContent";

interface HowItWorksModalProps {
  open: boolean;
  onClose: () => void;
  returnFocusRef?: React.RefObject<HTMLElement | null>;
}

/** Large scrollable modal with the approved How It Works content. */
export function HowItWorksModal({ open, onClose, returnFocusRef }: HowItWorksModalProps) {
  return (
    <Modal
      open={open}
      title="How LabelVerify Works"
      description="Prototype decision-support overview for compliance review"
      onClose={onClose}
      returnFocusRef={returnFocusRef}
      size="xl"
    >
      <HowItWorksContent />
    </Modal>
  );
}
