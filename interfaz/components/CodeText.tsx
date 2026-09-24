"use client";
import { useMemo } from 'react';
import { highlightCode } from '@/lib/helios/highlight';

/** React text nodes preserve the source and never execute file contents. */
export function CodeText({ source, language }: { source: string; language?: string }) {
  const tokens = useMemo(() => highlightCode(source, language), [source, language]);
  return <>{tokens.map((token, index) => <span key={index} className={token.kind ? `syntax-${token.kind}` : undefined}>{token.text}</span>)}</>;
}
