/**
 * Dataset A — closed-form textbook fixture (`docs/FIXTURES.md` §1).
 *
 * The exact rational weights come out to clean fractions under the
 * diagonal covariance assumption. These constants are the arbiter of
 * correctness for every Quant Engine test; do not re-derive them in test
 * files.
 */

import type { CovarianceMatrix } from "../types.js";

export const TOLERANCE_SCALAR = 1e-6;
export const TOLERANCE_WEIGHT_SUM = 1e-9;
export const TOLERANCE_SYMMETRY = 1e-10;
export const TOLERANCE_PSD = 1e-8;

export interface DatasetA {
  readonly tickers: readonly ["S1", "S2", "S3"];
  readonly riskFreeRate: number;
  readonly expectedReturns: readonly [number, number, number];
  readonly stdDevs: readonly [number, number, number];
  readonly correlation: number[][];
  readonly covariance: CovarianceMatrix;

  readonly orpWeights: Readonly<Record<"S1" | "S2" | "S3", number>>;
  readonly orpExpectedReturn: number;
  readonly orpStdDev: number;
  readonly orpVariance: number;
  readonly orpSharpe: number;

  readonly mvpWeights: Readonly<Record<"S1" | "S2" | "S3", number>>;
  readonly mvpExpectedReturn: number;
  readonly mvpStdDev: number;
  readonly mvpVariance: number;
}

const orpVariance = 0.013376;
const orpExpectedReturn = 0.1236;
const mvpExpectedReturn = 3.41 / 29.0;
const mvpVariance = 10.44 / 841.0;

export const datasetA: DatasetA = {
  tickers: ["S1", "S2", "S3"],
  riskFreeRate: 0.04,
  expectedReturns: [0.10, 0.13, 0.16],
  stdDevs: [0.15, 0.20, 0.30],
  correlation: [
    [1, 0, 0],
    [0, 1, 0],
    [0, 0, 1],
  ],
  covariance: {
    tickers: ["S1", "S2", "S3"],
    matrix: [
      [0.0225, 0.0, 0.0],
      [0.0, 0.04, 0.0],
      [0.0, 0.0, 0.09],
    ],
  },

  orpWeights: { S1: 32 / 75, S2: 9 / 25, S3: 16 / 75 },
  orpExpectedReturn,
  orpStdDev: Math.sqrt(orpVariance),
  orpVariance,
  orpSharpe: (orpExpectedReturn - 0.04) / Math.sqrt(orpVariance),

  mvpWeights: { S1: 16 / 29, S2: 9 / 29, S3: 4 / 29 },
  mvpExpectedReturn,
  mvpStdDev: Math.sqrt(mvpVariance),
  mvpVariance,
};

export interface DatasetACAPM {
  readonly riskFreeRate: number;
  readonly marketExpectedReturn: number;
  readonly marketStdDev: number;
  readonly marketVariance: number;
  readonly beta: number;
  readonly alpha: number;
  readonly firmSpecificVar: number;
  readonly requiredReturn: number;
  readonly totalExpectedReturn: number;
  readonly systematicVariance: number;
  readonly totalVariance: number;
  readonly stdDev: number;
}

export const datasetACAPM: DatasetACAPM = {
  riskFreeRate: 0.04,
  marketExpectedReturn: 0.10,
  marketStdDev: 0.18,
  marketVariance: 0.0324,
  beta: 1.2,
  alpha: 0.02,
  firmSpecificVar: 0.01,
  requiredReturn: 0.112,
  totalExpectedReturn: 0.132,
  systematicVariance: 0.046656,
  totalVariance: 0.056656,
  stdDev: Math.sqrt(0.056656),
};
