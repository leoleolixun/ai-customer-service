export interface HandoffSummaryLabels {
  customer: string;
  ai: string;
}

const ROLE_PREFIX = /^(Customer|user|AI|ai):\s*/;

export function localizeHandoffSummary(
  summary: string,
  labels: HandoffSummaryLabels,
): string {
  return summary.split('\n').map((line) => {
    const match = ROLE_PREFIX.exec(line);
    if (!match) return line;
    const label = match[1] === 'Customer' || match[1] === 'user' ? labels.customer : labels.ai;
    return `${label}: ${line.slice(match[0].length)}`;
  }).join('\n');
}
