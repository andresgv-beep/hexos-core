export type NasFileCopy = { file_id: string; name: string; path: string; device: string; size_bytes: number; text_available: boolean; observed_at: string };
function record(value: unknown): value is Record<string, unknown> { return value !== null && typeof value === 'object'; }
export async function listFileCopies(signal?: AbortSignal): Promise<NasFileCopy[]> {
  const response = await fetch('/api/helios/files', { signal });
  const data = await response.json();
  if (!response.ok || !Array.isArray(data)) throw new Error('No se pudieron cargar los archivos');
  return data.filter((item): item is NasFileCopy => record(item) && typeof item.file_id === 'string' &&
    /^[a-f0-9]{32}$/.test(item.file_id) && ['name','path','device','observed_at'].every(key => typeof item[key] === 'string') &&
    typeof item.size_bytes === 'number' && typeof item.text_available === 'boolean');
}
export async function readFilePage(id: string, offset=0, signal?: AbortSignal): Promise<{text:string;next_offset:number|null}> {
  if (!/^[a-f0-9]{32}$/.test(id)) throw new Error('Identificador no válido');
  const response = await fetch(`/api/helios/files/${id}/text?offset=${offset}`, { signal });
  const data = await response.json();
  if (!response.ok) throw new Error(record(data) && typeof data.error === 'string' ? data.error : 'No se pudo leer el documento');
  if (!record(data) || typeof data.text !== 'string' || !(data.next_offset === null ||
    (typeof data.next_offset === 'number' && Number.isSafeInteger(data.next_offset) && data.next_offset > offset)))
    throw new Error('Fragmento de documento inválido');
  return {text:data.text,next_offset:data.next_offset as number|null};
}
