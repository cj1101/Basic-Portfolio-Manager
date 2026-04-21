import { ClipboardList, Sliders, Info } from "lucide-react";
import { useState } from "react";
import { Slider } from "./ui/Slider";
import { NumberInput } from "./ui/NumberInput";
import { Tooltip } from "./ui/Tooltip";
import { usePortfolio } from "@/state/portfolioContext";
import { Questionnaire } from "./Questionnaire";

const SLIDER_MARKS = [
  { value: 1, label: "1" },
  { value: 3, label: "3" },
  { value: 5, label: "5" },
  { value: 7, label: "7" },
  { value: 10, label: "10" },
];

export function RiskControls() {
  const { riskProfile, setRiskAversion, setTargetReturn } = usePortfolio();
  const [showQuestionnaire, setShowQuestionnaire] = useState(false);

  return (
    <section
      aria-labelledby="risk-controls-heading"
      className="card mb-6 flex flex-col gap-5 p-5"
    >
      <header className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Sliders size={18} className="text-brand-600" aria-hidden />
          <h2 id="risk-controls-heading" className="text-lg font-semibold text-slate-900">
            Your risk profile
          </h2>
          <Tooltip label="A is the Arrow-Pratt coefficient of relative risk aversion. Higher A means more averse to volatility.">
            <Info size={14} className="text-slate-400" aria-label="About risk aversion" />
          </Tooltip>
        </div>
        <button
          type="button"
          onClick={() => setShowQuestionnaire(true)}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 shadow-sm transition-colors hover:border-brand-500 hover:text-brand-700"
        >
          <ClipboardList size={16} aria-hidden />
          Take the questionnaire
        </button>
      </header>

      <div className="grid gap-5 md:grid-cols-[1fr,1fr]">
        <Slider
          label="Risk aversion (A)"
          min={1}
          max={10}
          value={riskProfile.riskAversion}
          onChange={setRiskAversion}
          marks={SLIDER_MARKS}
          helperText="1 = very aggressive · 5 = balanced · 10 = very conservative"
        />
        <NumberInput
          label="Target annualized return"
          value={riskProfile.targetReturn}
          onChange={(v) => setTargetReturn(v)}
          mode="percent"
          suffix="%"
          min={0}
          max={100}
          step={0.5}
          placeholder="e.g. 15"
          helperText="If your target exceeds the ORP's expected return, leverage is used."
        />
      </div>

      {showQuestionnaire ? (
        <Questionnaire
          initialA={riskProfile.riskAversion}
          onClose={() => setShowQuestionnaire(false)}
          onSubmit={(A) => {
            setRiskAversion(A);
            setShowQuestionnaire(false);
          }}
        />
      ) : null}
    </section>
  );
}
