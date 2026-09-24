"use client";

import { useState } from 'react';
import { Brain, Database, FileSearch, Globe, History, Network, Server, StickyNote, Film, Wrench, Check, LoaderCircle, TriangleAlert } from 'lucide-react';
import type { ToolActivity } from '@/lib/helios/tools';

function identity(name: string) {
  const family = name.split('.')[0];
  switch (family) {
    case 'nas': return { Icon: Server, label: 'NAS' };
    case 'network': case 'device': return { Icon: Network, label: 'Red' };
    case 'document': return { Icon: FileSearch, label: 'Archivo' };
    case 'history': return { Icon: History, label: 'Historial' };
    case 'profile': return { Icon: Brain, label: 'Perfil' };
    case 'note': case 'core': return { Icon: StickyNote, label: 'Notas' };
    case 'media': return { Icon: Film, label: 'Vídeo' };
    case 'web': return { Icon: Globe, label: 'Web' };
    case 'work': case 'task': case 'report': case 'result': return { Icon: Database, label: 'Trabajo' };
    default: return { Icon: Wrench, label: family };
  }
}
const statusText = (tool: ToolActivity) => tool.status === 'running' ? 'Ejecutando' : tool.status === 'failed' ? 'Con error' : 'Completado';

/** Compact presentation of the same activity stream; clicking never executes a tool. */
export function ToolActivityPanel({ tools }: { tools: ToolActivity[] }) {
  const [selected, setSelected] = useState<string | null>(null);
  const active = tools.find(tool => tool.id === selected) ?? tools.find(tool => tool.status === 'running') ?? tools[tools.length - 1];
  const running = tools.filter(tool => tool.status === 'running').length;
  return <section className="hud-panel hud-activity" aria-label="Herramientas activas">
    <div className="hud-activity-heading"><h2>ACTIVIDAD</h2>
      {!!tools.length && <span>{tools.length} recientes{running ? ` · ${running} en curso` : ''}</span>}</div>
    {!tools.length && <p>Sin herramientas activas.</p>}
    <ul className="hud-tool-icons">{tools.map(tool => {
      const { Icon, label } = identity(tool.name);
      const Status = tool.status === 'running' ? LoaderCircle : tool.status === 'failed' ? TriangleAlert : Check;
      const description = `${tool.name} · ${statusText(tool)}${tool.seconds !== null ? ` · ${tool.seconds.toFixed(1)} s` : ''}`;
      return <li key={tool.id} data-status={tool.status}>
        <button type="button" aria-label={description} title={description} aria-pressed={active?.id === tool.id}
          onClick={() => setSelected(tool.id)}>
          <Icon size={23} aria-hidden="true" /><Status size={12} className="hud-tool-status" aria-hidden="true" />
          <span>{label}</span>
        </button>
      </li>;
    })}</ul>
    {active && <div className="hud-tool-detail" role="status"><strong>{active.name}</strong>
      <span>{statusText(active)}{active.seconds !== null && ` · ${active.seconds.toFixed(1)} s`}</span></div>}
  </section>;
}
