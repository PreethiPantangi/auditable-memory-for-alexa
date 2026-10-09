export interface MemoryActionResult {
  intent: string;
  category?: string;
  result?: {
    success?: boolean;
    data?: unknown;
    code?: string;
    message?: string;
  };
}

export function isEmptyRecall(action: MemoryActionResult): boolean {
  if (action.intent.toLowerCase() !== "recall") {
    return false;
  }

  const result = action.result;

  if (!result) return false;

  return (
    result.success === true &&
    (result.data === null ||
      (Array.isArray(result.data) && result.data.length === 0))
  );
}
