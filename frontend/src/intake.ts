/**
 * Source intake. The review API accepts one PNG or JPEG (max 5 MiB, 20 megapixels).
 * People bring other things: PDFs, text notes, other image formats, screen recordings.
 * Everything here turns such a file into ONE honest image of its content, in the browser,
 * and says what it did. No content is invented, summarized or altered: a PDF page is rendered,
 * text is typeset as written, a video contributes the single frame the reviewer picked.
 */

export const MAX_BYTES = 5 * 1024 * 1024;
export const MAX_PIXELS = 20_000_000;

export type Intake =
  | { kind: 'ready'; file: File; note: string | null }
  | { kind: 'video'; file: File }
  | { kind: 'unsupported'; message: string };

const TEXT_EXT = /\.(txt|md|markdown|csv|tsv|json|log|eml|html?|xml|ya?ml)$/i;
const WORD_EXT = /\.(docx?|odt|rtf|pages)$/i;
const SHEET_EXT = /\.(xlsx?|ods|numbers|pptx?|key)$/i;

function canvasToFile(canvas: HTMLCanvasElement, name: string, type: 'image/png' | 'image/jpeg', quality?: number): Promise<File> {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => (blob ? resolve(new File([blob], name, { type })) : reject(new Error('Could not encode the image.'))), type, quality);
  });
}

/** Keep an image inside the API's limits: scale to 20 MP, then step JPEG quality/size down under 5 MiB. */
async function fit(canvas: HTMLCanvasElement, baseName: string): Promise<File> {
  let work = canvas;
  const shrink = (scale: number) => {
    const next = document.createElement('canvas');
    next.width = Math.max(1, Math.round(work.width * scale));
    next.height = Math.max(1, Math.round(work.height * scale));
    next.getContext('2d')!.drawImage(work, 0, 0, next.width, next.height);
    work = next;
  };
  if (work.width * work.height > MAX_PIXELS) shrink(Math.sqrt(MAX_PIXELS / (work.width * work.height)));
  let file = await canvasToFile(work, `${baseName}.png`, 'image/png');
  for (let i = 0; file.size > MAX_BYTES && i < 6; i++) {
    if (i > 0) shrink(0.8);
    file = await canvasToFile(work, `${baseName}.jpg`, 'image/jpeg', 0.9);
  }
  if (file.size > MAX_BYTES) throw new Error('This file is still over 5 MB after shrinking. Crop it to the relevant part and try again.');
  return file;
}

function drawToCanvas(source: CanvasImageSource, width: number, height: number): HTMLCanvasElement {
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d')!;
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, width, height);
  ctx.drawImage(source, 0, 0, width, height);
  return canvas;
}

async function fromImage(file: File, base: string): Promise<Intake> {
  const direct = (file.type === 'image/png' || file.type === 'image/jpeg') && file.size <= MAX_BYTES;
  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(file);
  } catch {
    return { kind: 'unsupported', message: `This browser cannot open ${file.type || 'this image format'}. Save it as PNG or JPEG and try again.` };
  }
  if (direct && bitmap.width * bitmap.height <= MAX_PIXELS) return { kind: 'ready', file, note: null };
  const out = await fit(drawToCanvas(bitmap, bitmap.width, bitmap.height), base);
  return { kind: 'ready', file: out, note: `Converted in your browser from ${file.type || 'an image'} (${Math.round(file.size / 1024)} KB) to fit the upload limits.` };
}

const TEXT_MAX_LINES = 110;

function typeset(text: string): { canvas: HTMLCanvasElement; truncated: boolean } {
  const width = 1200, pad = 48, lineHeight = 26;
  const measure = document.createElement('canvas').getContext('2d')!;
  const font = '18px ui-monospace, Menlo, Consolas, monospace';
  measure.font = font;
  const lines: string[] = [];
  for (const raw of text.replace(/\r\n?/g, '\n').replace(/\t/g, '    ').split('\n')) {
    let line = '';
    for (const word of raw.split(/(\s+)/)) {
      if (measure.measureText(line + word).width > width - 2 * pad && line) {
        lines.push(line);
        line = word.trimStart();
      } else {
        line += word;
      }
    }
    lines.push(line);
  }
  const truncated = lines.length > TEXT_MAX_LINES;
  const shown = lines.slice(0, TEXT_MAX_LINES);
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = pad * 2 + shown.length * lineHeight;
  const ctx = canvas.getContext('2d')!;
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = '#111827';
  ctx.font = font;
  ctx.textBaseline = 'top';
  shown.forEach((line, i) => ctx.fillText(line, pad, pad + i * lineHeight));
  return { canvas, truncated };
}

async function fromText(file: File, base: string): Promise<Intake> {
  const text = await file.text();
  if (!text.trim()) return { kind: 'unsupported', message: 'This file is empty.' };
  const { canvas, truncated } = typeset(text);
  return {
    kind: 'ready',
    file: await fit(canvas, base),
    note: truncated
      ? `Typeset in your browser as an image. Only the first ${TEXT_MAX_LINES} lines are included.`
      : 'Typeset in your browser as an image, word for word.',
  };
}

interface PdfPage {
  getViewport(o: { scale: number }): { width: number; height: number };
  render(o: { canvasContext: CanvasRenderingContext2D; canvas: HTMLCanvasElement; viewport: unknown }): { promise: Promise<void> };
}
interface PdfModule {
  GlobalWorkerOptions: { workerSrc: string };
  getDocument(o: { data: Uint8Array }): { promise: Promise<{ numPages: number; getPage(n: number): Promise<PdfPage> }> };
}

async function fromPdf(file: File, base: string): Promise<Intake> {
  // pdf.js is vendored under public/vendor and fetched only when a PDF is dropped.
  // A fully qualified URL avoids Vite adding ?import to this public asset.
  const lib = new URL(`${import.meta.env.BASE_URL}vendor/pdfjs/pdf.min.mjs`, window.location.href).href;
  const pdfjs = (await import(/* @vite-ignore */ lib)) as PdfModule;
  pdfjs.GlobalWorkerOptions.workerSrc = `${import.meta.env.BASE_URL}vendor/pdfjs/pdf.worker.min.mjs`;
  const doc = await pdfjs.getDocument({ data: new Uint8Array(await file.arrayBuffer()) }).promise;
  const page = await doc.getPage(1);
  const viewport = page.getViewport({ scale: 2 });
  const canvas = document.createElement('canvas');
  canvas.width = Math.ceil(viewport.width);
  canvas.height = Math.ceil(viewport.height);
  const ctx = canvas.getContext('2d')!;
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  await page.render({ canvasContext: ctx, canvas, viewport }).promise;
  const pages = doc.numPages;
  return {
    kind: 'ready',
    file: await fit(canvas, base),
    note: pages > 1 ? `Page 1 of ${pages} rendered in your browser. The other pages are not included.` : 'The PDF page was rendered in your browser as an image.',
  };
}

/** Decide what to do with a dropped file. */
export async function prepare(file: File): Promise<Intake> {
  const name = file.name || 'source';
  const base = name.replace(/\.[^.]+$/, '') || 'source';
  try {
    if (file.type.startsWith('video/') || /\.(mp4|mov|webm|m4v|mkv)$/i.test(name)) return { kind: 'video', file };
    if (file.type === 'application/pdf' || /\.pdf$/i.test(name)) return await fromPdf(file, base);
    if (file.type.startsWith('image/')) return await fromImage(file, base);
    if (file.type.startsWith('text/') || file.type === 'application/json' || TEXT_EXT.test(name)) return await fromText(file, base);
    if (WORD_EXT.test(name)) return { kind: 'unsupported', message: 'Word documents cannot be read in the browser. Export it as a PDF (File, then Save as PDF) and drop the PDF here.' };
    if (SHEET_EXT.test(name)) return { kind: 'unsupported', message: 'Spreadsheets and slides are not supported. Export the relevant page as a PDF or take a screenshot.' };
    return { kind: 'unsupported', message: `Membrane cannot read ${file.type || 'this file type'}. Use an image, a PDF, a text file or a video.` };
  } catch (err) {
    return { kind: 'unsupported', message: err instanceof Error ? `Could not read ${name}: ${err.message}` : `Could not read ${name}.` };
  }
}

/** Capture the frame a <video> element is currently showing. */
export async function captureFrame(video: HTMLVideoElement, sourceName: string): Promise<{ file: File; note: string }> {
  if (!video.videoWidth) throw new Error('The video has not loaded a frame yet.');
  const canvas = drawToCanvas(video, video.videoWidth, video.videoHeight);
  const base = (sourceName.replace(/\.[^.]+$/, '') || 'video') + `-frame-${video.currentTime.toFixed(1)}s`;
  return { file: await fit(canvas, base), note: `One frame of ${sourceName}, taken at ${video.currentTime.toFixed(1)} s. The rest of the video is not included.` };
}
