import React from 'react';

/**
 * Renders RHCSA task instruction text (markdown-like) into structured HTML.
 * Handles: paragraphs, bullet lists (- item), numbered lists (1. item), inline `code`.
 */
const Instructions: React.FC<{ text: string }> = ({ text }) => {
  const blocks = parseBlocks(text.trim());
  return (
    <div className="space-y-3 text-sm leading-relaxed text-slate-300">
      {blocks.map((block, i) => {
        if (block.type === 'paragraph') {
          return <p key={i} className="text-slate-300">{renderInline(block.content)}</p>;
        }
        if (block.type === 'bullet') {
          return (
            <ul key={i} className="space-y-1.5 pl-1">
              {block.items.map((item, j) => (
                <li key={j} className="flex gap-2.5 items-start">
                  <span className="mt-1.5 flex-shrink-0 w-1.5 h-1.5 rounded-full bg-red-500/70" />
                  <span>{renderInline(item)}</span>
                </li>
              ))}
            </ul>
          );
        }
        if (block.type === 'numbered') {
          return (
            <ol key={i} className="space-y-2 pl-1">
              {block.items.map((item, j) => (
                <li key={j} className="flex gap-3 items-start">
                  <span className="flex-shrink-0 w-5 h-5 rounded bg-slate-700 border border-slate-600 text-[10px] font-bold text-slate-400 flex items-center justify-center mt-0.5">
                    {j + 1}
                  </span>
                  <span className="flex-1">{renderInline(item)}</span>
                </li>
              ))}
            </ol>
          );
        }
        return null;
      })}
    </div>
  );
};

// ── types ──────────────────────────────────────────────────────────────────

type Block =
  | { type: 'paragraph'; content: string }
  | { type: 'bullet';   items: string[] }
  | { type: 'numbered'; items: string[] };

// ── parser ─────────────────────────────────────────────────────────────────

function parseBlocks(text: string): Block[] {
  const lines = text.split('\n');
  const blocks: Block[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Skip blank lines
    if (line.trim() === '') { i++; continue; }

    // Bullet list block
    if (/^- /.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^- /.test(lines[i])) {
        items.push(lines[i].replace(/^- /, '').trim());
        i++;
      }
      blocks.push({ type: 'bullet', items });
      continue;
    }

    // Numbered list block
    if (/^\d+\. /.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\d+\. /.test(lines[i])) {
        items.push(lines[i].replace(/^\d+\. /, '').trim());
        i++;
      }
      blocks.push({ type: 'numbered', items });
      continue;
    }

    // Paragraph: collect consecutive non-list, non-blank lines
    const parts: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() !== '' &&
      !/^- /.test(lines[i]) &&
      !/^\d+\. /.test(lines[i])
    ) {
      parts.push(lines[i].trim());
      i++;
    }
    if (parts.length) blocks.push({ type: 'paragraph', content: parts.join(' ') });
  }

  return blocks;
}

// ── inline renderer: `code` and bold ──────────────────────────────────────

function renderInline(text: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  const re = /`([^`]+)`/g;
  let last = 0, m: RegExpExecArray | null;

  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    parts.push(
      <code key={m.index} className="px-1.5 py-0.5 rounded bg-slate-700 text-red-300 font-mono text-xs border border-slate-600">
        {m[1]}
      </code>
    );
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

export default Instructions;
