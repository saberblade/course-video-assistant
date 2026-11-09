export type KnowledgeStatus = "ok" | "warn" | "bad";

export interface KnowledgeNode {
  id: string;
  name: string;
  /** viewBox 坐标（1200 × 700） */
  x: number;
  y: number;
  /** 在课程原文中出现的次数 */
  hits: number;
  status: KnowledgeStatus;
  module: string;
  chapter: string;
  /** 回到视频的时间点（秒） */
  time: number;
  quote: string;
}

export interface KnowledgeModule {
  id: string;
  name: string;
  labelX: number;
  labelY: number;
  path: string;
  deep?: boolean;
}

export interface KnowledgeLink {
  from: string;
  to: string;
  cross?: boolean;
}

export const STATUS_META: Record<KnowledgeStatus, { label: string; color: string; soft: string }> = {
  ok: { label: "已掌握", color: "#159263", soft: "rgba(21, 146, 99, 0.14)" },
  warn: { label: "待复习", color: "#ad7008", soft: "rgba(173, 112, 8, 0.14)" },
  bad: { label: "薄弱点", color: "#b53f34", soft: "rgba(181, 63, 52, 0.14)" },
};

export const knowledgeModules: KnowledgeModule[] = [
  {
    id: "basics",
    name: "评估基础",
    labelX: 318,
    labelY: 186,
    path:
      "M 300 150 L 470 130 L 452 300 L 430 500 L 430 570 L 300 510 L 230 420 L 200 320 L 250 210 Z",
  },
  {
    id: "metrics",
    name: "核心指标",
    labelX: 628,
    labelY: 198,
    path:
      "M 470 130 L 560 170 L 700 140 L 860 175 L 800 360 L 820 600 L 680 570 L 560 610 L 430 570 L 430 500 L 452 300 Z",
    deep: true,
  },
  {
    id: "decision",
    name: "应用判断",
    labelX: 906,
    labelY: 235,
    path:
      "M 860 175 L 980 250 L 1000 360 L 940 470 L 960 560 L 820 600 L 800 360 Z",
  },
];

/** 整体外轮廓：用来叠一层统一的发光边缘 */
export const knowledgeOutline =
  "M 300 150 L 470 130 L 560 170 L 700 140 L 860 175 L 980 250 L 1000 360 L 940 470 L 960 560 L 820 600 L 680 570 L 560 610 L 430 570 L 300 510 L 230 420 L 200 320 L 250 210 Z";

export const knowledgeNodes: KnowledgeNode[] = [
  {
    id: "classification",
    name: "分类任务",
    x: 290,
    y: 248,
    hits: 9,
    status: "ok",
    module: "basics",
    chapter: "00:00 章节提要",
    time: 0,
    quote: "今天我们来学习分类模型的评估方法，重点理解精确率、召回率和 F1 值。",
  },
  {
    id: "matrix",
    name: "混淆矩阵",
    x: 302,
    y: 382,
    hits: 7,
    status: "warn",
    module: "basics",
    chapter: "00:00 章节提要",
    time: 12,
    quote: "精确率等于真正例除以真正例与假正例之和。",
  },
  {
    id: "accuracy",
    name: "准确率",
    x: 352,
    y: 478,
    hits: 5,
    status: "ok",
    module: "basics",
    chapter: "00:00 章节提要",
    time: 22,
    quote: "分类模型的评估不能只看准确率，还要看正负样本的分布情况。",
  },
  {
    id: "imbalance",
    name: "样本不平衡",
    x: 394,
    y: 298,
    hits: 4,
    status: "bad",
    module: "basics",
    chapter: "00:00 章节提要",
    time: 32,
    quote: "当正负样本比例悬殊时，准确率会被多数类主导，无法反映模型对少数类的识别能力。",
  },
  {
    id: "precision",
    name: "精确率",
    x: 548,
    y: 260,
    hits: 12,
    status: "ok",
    module: "metrics",
    chapter: "00:00 章节提要",
    time: 33,
    quote: "精确率等于真正例除以真正例与假正例之和。",
  },
  {
    id: "recall",
    name: "召回率",
    x: 684,
    y: 294,
    hits: 11,
    status: "warn",
    module: "metrics",
    chapter: "01:00 章节提要",
    time: 62,
    quote: "召回率等于真正例除以真正例与假反例之和。",
  },
  {
    id: "f1",
    name: "F1 值",
    x: 600,
    y: 426,
    hits: 8,
    status: "ok",
    module: "metrics",
    chapter: "02:00 章节提要",
    time: 128,
    quote: "F1 值是精确率和召回率的调和平均数，用于综合衡量这两个指标。",
  },
  {
    id: "threshold",
    name: "阈值选择",
    x: 742,
    y: 404,
    hits: 6,
    status: "bad",
    module: "metrics",
    chapter: "01:00 章节提要",
    time: 84,
    quote: "精确率关注预测为正的样本中有多少是真的，召回率关注真实为正的样本中有多少被找出来。",
  },
  {
    id: "harmonic",
    name: "调和平均",
    x: 514,
    y: 524,
    hits: 4,
    status: "warn",
    module: "metrics",
    chapter: "02:00 章节提要",
    time: 128,
    quote: "F1 值用调和平均而不是算术平均，因为调和平均对较小的一方更敏感。",
  },
  {
    id: "fn-cost",
    name: "漏报代价",
    x: 866,
    y: 292,
    hits: 5,
    status: "warn",
    module: "decision",
    chapter: "02:00 章节提要",
    time: 145,
    quote: "实际应用中，要根据业务代价决定更关注漏报还是误报，而不是只看准确率。",
  },
  {
    id: "fp-cost",
    name: "误报代价",
    x: 940,
    y: 368,
    hits: 4,
    status: "ok",
    module: "decision",
    chapter: "02:00 章节提要",
    time: 148,
    quote: "误报会带来人工复核成本，漏报则可能造成更严重的业务损失。",
  },
  {
    id: "tradeoff",
    name: "代价权衡",
    x: 856,
    y: 448,
    hits: 6,
    status: "warn",
    module: "decision",
    chapter: "02:00 章节提要",
    time: 152,
    quote: "精确率和召回率往往此消彼长，需要结合业务目标确定平衡点。",
  },
  {
    id: "decision",
    name: "业务决策",
    x: 900,
    y: 540,
    hits: 7,
    status: "bad",
    module: "decision",
    chapter: "02:00 章节提要",
    time: 157,
    quote: "实际应用中，要根据业务代价决定更关注漏报还是误报，而不是只看准确率。",
  },
];

export const knowledgeLinks: KnowledgeLink[] = [
  { from: "classification", to: "matrix" },
  { from: "classification", to: "imbalance" },
  { from: "matrix", to: "accuracy" },
  { from: "imbalance", to: "accuracy" },
  { from: "matrix", to: "precision", cross: true },
  { from: "accuracy", to: "precision", cross: true },
  { from: "precision", to: "recall" },
  { from: "precision", to: "f1" },
  { from: "recall", to: "f1" },
  { from: "recall", to: "threshold" },
  { from: "threshold", to: "f1" },
  { from: "f1", to: "harmonic" },
  { from: "f1", to: "tradeoff", cross: true },
  { from: "threshold", to: "fn-cost", cross: true },
  { from: "fn-cost", to: "fp-cost" },
  { from: "fn-cost", to: "tradeoff" },
  { from: "tradeoff", to: "decision" },
  { from: "fp-cost", to: "decision" },
];

const nodeIndex = new Map(knowledgeNodes.map((node) => [node.id, node]));

export function findNode(id: string): KnowledgeNode | undefined {
  return nodeIndex.get(id);
}

/** 连线控制点：在中点基础上向垂直方向偏移，形成弧线 */
export function linkPath(from: KnowledgeNode, to: KnowledgeNode): string {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const mx = (from.x + to.x) / 2;
  const my = (from.y + to.y) / 2;
  const length = Math.hypot(dx, dy) || 1;
  const bend = Math.min(46, length * 0.18);
  const cx = mx + (-dy / length) * bend;
  const cy = my + (dx / length) * bend;
  return `M ${from.x} ${from.y} Q ${cx.toFixed(1)} ${cy.toFixed(1)} ${to.x} ${to.y}`;
}

export const statusCounts = knowledgeNodes.reduce(
  (acc, node) => {
    acc[node.status] += 1;
    return acc;
  },
  { ok: 0, warn: 0, bad: 0 } as Record<KnowledgeStatus, number>,
);
