import { useCallback, useState } from "react";
import { Header } from "./components/Header";
import { IntroBanner } from "./components/IntroBanner";
import { TickerBar } from "./components/TickerBar";
import { RiskControls } from "./components/RiskControls";
import { TABS, Tabs, type TabId } from "./components/Tabs";
import { OverviewTab } from "./components/tabs/OverviewTab";
import { EfficientFrontierTab } from "./components/tabs/EfficientFrontierTab";
import { CapmAlphaTab } from "./components/tabs/CapmAlphaTab";
import { AssetAllocationTab } from "./components/tabs/AssetAllocationTab";
import { ApisDataTab } from "./components/tabs/ApisDataTab";
import { CourseMetricsTab } from "./components/tabs/CourseMetricsTab";
import { TechnicalAnalysisTab } from "./components/tabs/TechnicalAnalysisTab";
import { ChatShell } from "./components/chat/ChatShell";
import { ResultBoundary } from "./components/ui/ResultBoundary";
import type {
  AnalyticsPerformanceResult,
  HistoricalResponse,
  LoadedPanelData,
  ValuationResult,
} from "./types/contracts";

function TabPanel({
  id,
  hidden,
  children,
}: {
  id: TabId;
  hidden: boolean;
  children: React.ReactNode;
}) {
  return (
    <div
      role="tabpanel"
      id={`panel-${id}`}
      aria-labelledby={`tab-${id}`}
      hidden={hidden}
      tabIndex={0}
      className="focus:outline-none"
    >
      {!hidden ? children : null}
    </div>
  );
}

function App() {
  const [active, setActive] = useState<TabId>("overview");
  const [chatPanelData, setChatPanelData] = useState<LoadedPanelData>({
    availability: { analytics: false, valuation: false, technical: false },
  });

  const handleAnalyticsLoaded = useCallback((analytics: AnalyticsPerformanceResult | null) => {
    setChatPanelData((prev) => ({
      ...prev,
      availability: { ...prev.availability, analytics: analytics != null },
      ...(analytics ? { analytics } : {}),
      ...(analytics == null ? { analytics: undefined } : {}),
    }));
  }, []);

  const handleCourseValuationLoaded = useCallback((valuation: ValuationResult | null) => {
    setChatPanelData((prev) => ({
      ...prev,
      availability: {
        ...prev.availability,
        valuation: valuation != null || prev.availability.valuation,
      },
      ...(valuation ? { valuation } : {}),
    }));
  }, []);

  const handleTechnicalLoaded = useCallback(
    (
      payload: {
        selectedTicker: string;
        stockDataMap: Record<string, HistoricalResponse>;
        benchmark: HistoricalResponse;
      } | null,
    ) => {
      setChatPanelData((prev) => ({
        ...prev,
        availability: { ...prev.availability, technical: payload != null },
        ...(payload
          ? {
            technicalSelectedTicker: payload.selectedTicker,
            technicalHistory: payload.stockDataMap,
            technicalBenchmark: payload.benchmark,
          }
        : {
            technicalSelectedTicker: undefined,
            technicalHistory: undefined,
            technicalBenchmark: undefined,
          }),
      }));
    },
    [],
  );

  const handleTechnicalValuationLoaded = useCallback((valuation: ValuationResult | null) => {
    if (!valuation) return;
    setChatPanelData((prev) => ({
      ...prev,
      availability: { ...prev.availability, valuation: true },
      valuation,
    }));
  }, []);

  return (
    <div className="min-h-screen bg-slate-50 pb-24 text-slate-800">
      <Header />
      <main
        role="main"
        className="mx-auto mt-6 max-w-6xl px-6"
        aria-label="Portfolio manager client report"
      >
        <IntroBanner />
        <TickerBar />
        <RiskControls />
        <Tabs value={active} onChange={setActive} />
        <section
          className="card p-6"
          aria-live="polite"
          aria-label={TABS.find((t) => t.id === active)?.label}
        >
          <TabPanel id="overview" hidden={active !== "overview"}>
            <ResultBoundary>
              <OverviewTab />
            </ResultBoundary>
          </TabPanel>
          <TabPanel id="frontier" hidden={active !== "frontier"}>
            <ResultBoundary>
              <EfficientFrontierTab />
            </ResultBoundary>
          </TabPanel>
          <TabPanel id="capm" hidden={active !== "capm"}>
            <ResultBoundary>
              <CapmAlphaTab />
            </ResultBoundary>
          </TabPanel>
          <TabPanel id="allocation" hidden={active !== "allocation"}>
            <ResultBoundary>
              <AssetAllocationTab />
            </ResultBoundary>
          </TabPanel>
          <TabPanel id="course" hidden={active !== "course"}>
            <ResultBoundary>
              <CourseMetricsTab
                onAnalyticsLoaded={handleAnalyticsLoaded}
                onValuationLoaded={handleCourseValuationLoaded}
              />
            </ResultBoundary>
          </TabPanel>
          <TabPanel id="technical" hidden={active !== "technical"}>
            <ResultBoundary>
              <TechnicalAnalysisTab
                onTechnicalDataLoaded={handleTechnicalLoaded}
                onValuationLoaded={handleTechnicalValuationLoaded}
              />
            </ResultBoundary>
          </TabPanel>
          <TabPanel id="data" hidden={active !== "data"}>
            <ApisDataTab />
          </TabPanel>
        </section>
      </main>
      <ChatShell activeTab={active} loadedPanelData={chatPanelData} />
    </div>
  );
}

export default App;
