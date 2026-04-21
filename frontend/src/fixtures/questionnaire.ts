/**
 * Risk-aversion questionnaire. 6 questions, each answer awards 1..10 points.
 * Final A = round(mean(points)) clamped to [1, 10].
 *
 * Higher points = MORE risk averse (i.e., larger A score). This matches the
 * SPEC.md §8 convention that a high-A investor is conservative.
 *
 * Scoring table is declarative so it is easy to review and auditable.
 */

export interface QuestionOption {
  id: string;
  label: string;
  /** Points contribution to the final A score, 1 = most aggressive, 10 = most conservative. */
  score: number;
}

export interface Question {
  id: string;
  prompt: string;
  description?: string;
  options: QuestionOption[];
}

export const questionnaire: Question[] = [
  {
    id: "horizon",
    prompt: "What is your investment horizon?",
    description: "How long before you expect to need most of this capital?",
    options: [
      { id: "h1", label: "Less than 2 years", score: 10 },
      { id: "h2", label: "2 to 5 years", score: 7 },
      { id: "h3", label: "5 to 10 years", score: 4 },
      { id: "h4", label: "10 to 20 years", score: 2 },
      { id: "h5", label: "More than 20 years", score: 1 },
    ],
  },
  {
    id: "drawdown",
    prompt: "If your portfolio dropped 30% in a month, you would…",
    options: [
      { id: "d1", label: "Sell everything immediately to stop further losses", score: 10 },
      { id: "d2", label: "Sell a portion to reduce exposure", score: 8 },
      { id: "d3", label: "Hold your positions and wait it out", score: 5 },
      { id: "d4", label: "Rebalance back to target weights", score: 3 },
      { id: "d5", label: "Buy more while prices are depressed", score: 1 },
    ],
  },
  {
    id: "liquidity",
    prompt: "How likely are you to need a large portion of this money in the next 12 months?",
    options: [
      { id: "l1", label: "Very likely — it is earmarked for a near-term purchase", score: 10 },
      { id: "l2", label: "Somewhat likely", score: 7 },
      { id: "l3", label: "Unlikely", score: 4 },
      { id: "l4", label: "Very unlikely — this is long-term capital", score: 1 },
    ],
  },
  {
    id: "income",
    prompt: "How stable is your primary income source?",
    options: [
      { id: "i1", label: "Unstable or irregular", score: 9 },
      { id: "i2", label: "Stable but depends on a single employer", score: 6 },
      { id: "i3", label: "Stable with multiple streams", score: 3 },
      { id: "i4", label: "Fully retired / income-independent from market", score: 2 },
    ],
  },
  {
    id: "experience",
    prompt: "How much prior experience do you have with volatile assets (equities, crypto, options)?",
    options: [
      { id: "e1", label: "None", score: 9 },
      { id: "e2", label: "Some — I have held stocks through a downturn", score: 5 },
      { id: "e3", label: "Significant — I actively trade or manage my own book", score: 2 },
    ],
  },
  {
    id: "goal",
    prompt: "What is the primary goal for this portfolio?",
    options: [
      { id: "g1", label: "Capital preservation (keep what I have)", score: 10 },
      { id: "g2", label: "Balanced growth and preservation", score: 6 },
      { id: "g3", label: "Aggressive growth", score: 2 },
      { id: "g4", label: "Maximum growth — I can tolerate large swings", score: 1 },
    ],
  },
];

export function scoreQuestionnaire(answers: Record<string, string>): number {
  const points: number[] = [];
  for (const q of questionnaire) {
    const chosenId = answers[q.id];
    if (!chosenId) continue;
    const opt = q.options.find((o) => o.id === chosenId);
    if (opt) points.push(opt.score);
  }
  if (points.length === 0) return 3;
  const mean = points.reduce((a, b) => a + b, 0) / points.length;
  return Math.max(1, Math.min(10, Math.round(mean)));
}
