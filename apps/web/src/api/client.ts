export interface HealthResponse {
  status: 'ok';
  service: string;
  version: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status?: number,
    public correlationId?: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export async function apiGet<T>(
  path: string,
  signal?: AbortSignal,
): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetch(`/api${path}`, {
      signal: signal
        ? AbortSignal.any([signal, controller.signal])
        : controller.signal,
      headers: { Accept: 'application/json' },
    });
    if (!response.ok)
      throw new ApiError(
        `API request failed (HTTP ${response.status}). Check the API service and try again.`,
        response.status,
        response.headers.get('x-correlation-id') ?? undefined,
      );
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (controller.signal.aborted)
      throw new ApiError(
        'The API did not respond within 8 seconds. Please try again.',
      );
    throw new ApiError(
      'Unable to reach the API or read its response. Check your connection and try again.',
    );
  } finally {
    window.clearTimeout(timeout);
  }
}

export async function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const data: unknown = await apiGet('/health', signal);
  if (
    typeof data !== 'object' ||
    data === null ||
    !('status' in data) ||
    data.status !== 'ok' ||
    !('service' in data) ||
    typeof data.service !== 'string' ||
    !('version' in data) ||
    typeof data.version !== 'string'
  )
    throw new Error('Unexpected API health response');
  return data as HealthResponse;
}
