/**
 * Root application composition for LabelVerify.
 * Architectural responsibility: mount the unified analyst workspace in AppShell;
 * fire privacy-safe access telemetry once per load without blocking UI.
 */
import { useEffect } from "react";
import { AppShell } from "./components/common/AppShell";
import { AnalystWorkspace } from "./pages/AnalystWorkspace";
import { recordSiteAccess } from "./services/api";

export default function App() {
  useEffect(() => {
    // Once per application load — never blocks rendering; failures are ignored.
    void recordSiteAccess("workspace");
  }, []);

  return (
    <AppShell>
      <AnalystWorkspace />
    </AppShell>
  );
}
