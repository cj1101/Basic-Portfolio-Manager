import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import clsx from "clsx";
import { ArrowLeft, ArrowRight, CheckCircle2, X } from "lucide-react";
import { questionnaire, scoreQuestionnaire } from "@/fixtures/questionnaire";

export interface QuestionnaireProps {
  initialA: number;
  onSubmit: (A: number) => void;
  onClose: () => void;
}

export function Questionnaire({ initialA, onSubmit, onClose }: QuestionnaireProps) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [index, setIndex] = useState(0);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const closeBtnRef = useRef<HTMLButtonElement | null>(null);

  const total = questionnaire.length;
  const current = questionnaire[index];

  const projectedA = useMemo(() => scoreQuestionnaire(answers), [answers]);
  const isLast = index === total - 1;

  useEffect(() => {
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeBtnRef.current?.focus();

    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    };
    document.addEventListener("keydown", handleKey);
    return () => {
      document.body.style.overflow = prevOverflow;
      document.removeEventListener("keydown", handleKey);
    };
  }, [onClose]);

  const handleSelect = useCallback(
    (questionId: string, optionId: string) => {
      setAnswers((prev) => ({ ...prev, [questionId]: optionId }));
    },
    [],
  );

  const goNext = useCallback(() => {
    if (index < total - 1) setIndex((i) => i + 1);
  }, [index, total]);
  const goBack = useCallback(() => {
    if (index > 0) setIndex((i) => i - 1);
  }, [index]);

  const submit = () => {
    onSubmit(projectedA);
  };

  if (!current) return null;
  const hasAnswer = answers[current.id] != null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="questionnaire-title"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={dialogRef}
        className="w-full max-w-lg animate-fade-in rounded-2xl bg-white shadow-2xl"
      >
        <div className="flex items-start justify-between border-b border-slate-100 px-6 py-4">
          <div>
            <h2 id="questionnaire-title" className="text-lg font-semibold text-slate-900">
              Risk questionnaire
            </h2>
            <p className="text-xs text-slate-500">
              Question {index + 1} of {total} · projected A = {projectedA} (was {initialA})
            </p>
          </div>
          <button
            ref={closeBtnRef}
            type="button"
            onClick={onClose}
            aria-label="Close questionnaire"
            className="rounded-full p-1 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
          >
            <X size={20} />
          </button>
        </div>

        <div className="px-6 py-5">
          <fieldset>
            <legend className="text-base font-medium text-slate-900">{current.prompt}</legend>
            {current.description ? (
              <p className="mt-1 text-sm text-slate-500">{current.description}</p>
            ) : null}
            <div className="mt-4 space-y-2">
              {current.options.map((opt) => {
                const selected = answers[current.id] === opt.id;
                return (
                  <label
                    key={opt.id}
                    className={clsx(
                      "flex cursor-pointer items-start gap-3 rounded-lg border px-3 py-2.5 text-sm transition-colors",
                      selected
                        ? "border-brand-500 bg-brand-50 text-brand-800"
                        : "border-slate-200 hover:border-slate-300 hover:bg-slate-50",
                    )}
                  >
                    <input
                      type="radio"
                      className="form-radio mt-0.5 text-brand-600 focus:ring-brand-500"
                      name={current.id}
                      value={opt.id}
                      checked={selected}
                      onChange={() => handleSelect(current.id, opt.id)}
                    />
                    <span className="flex-1">{opt.label}</span>
                  </label>
                );
              })}
            </div>
          </fieldset>

          <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
            <div
              className="h-full bg-brand-500 transition-all"
              style={{ width: `${((index + 1) / total) * 100}%` }}
              aria-hidden
            />
          </div>
        </div>

        <div className="flex items-center justify-between gap-2 border-t border-slate-100 bg-slate-50 px-6 py-3">
          <button
            type="button"
            onClick={goBack}
            disabled={index === 0}
            className="inline-flex items-center gap-1 rounded-md px-3 py-1.5 text-sm font-medium text-slate-600 transition-colors hover:bg-white disabled:cursor-not-allowed disabled:opacity-40"
          >
            <ArrowLeft size={14} /> Back
          </button>
          {isLast ? (
            <button
              type="button"
              onClick={submit}
              disabled={!hasAnswer}
              className="inline-flex items-center gap-1.5 rounded-md bg-brand-600 px-4 py-1.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-slate-300"
            >
              <CheckCircle2 size={16} /> Apply A = {projectedA}
            </button>
          ) : (
            <button
              type="button"
              onClick={goNext}
              disabled={!hasAnswer}
              className="inline-flex items-center gap-1 rounded-md bg-brand-600 px-3 py-1.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-slate-300"
            >
              Next <ArrowRight size={14} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
