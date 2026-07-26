import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "../../api/client";
import { SceneConfig, Transition, WorkflowInstance } from "../../types/api";
import { ShellProps } from "./types";

/**
 * Scene shell (docs/MEDIA.md Part 2) — the visual-novel / narrative player.
 *
 * The other shells lay work out for an operator; this one *plays* a workflow.
 * The mapping is exact and needs no new engine machinery:
 *
 *   scene = state · choice = transition · flag/inventory = metadata
 *   locked choice = a rule that blocks the transition
 *   save file = instance ("Continue" reopens one, "New game" creates one)
 *
 * Every choice still goes through `fireTransition`, so the engine's rules,
 * approvals and required forms gate the story exactly as they gate a business
 * process. When a rule blocks a move, its `reason` becomes the narrative
 * feedback ("The door is locked."), shown in the host page's banner — the rule
 * author is effectively writing game text. (Rendering it inside the dialogue
 * box would need `transitionError` on ShellProps; deferred so this doesn't
 * collide with WS-C's ownership of shells/types.ts.)
 */

const POSITION_STYLE: Record<string, React.CSSProperties> = {
  left: { left: "8%", transform: "translateX(0)" },
  centre: { left: "50%", transform: "translateX(-50%)" },
  right: { right: "8%", left: "auto", transform: "translateX(0)" },
};

/** Resolve `{{metadata.key}}` / `{{instance.reference_number}}` in scene text. */
function interpolate(text: string, instance: WorkflowInstance): string {
  if (!text) return "";
  const meta = instance.metadata_json ?? {};
  return text.replace(/\{\{\s*(metadata|instance)\.([\w.-]+)\s*\}\}/g, (whole, kind, key) => {
    const value = kind === "metadata" ? meta[key] : (instance as any)[key];
    return value === undefined || value === null ? whole : String(value);
  });
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * Scene assets may be a plain URL or a MediaAsset id. Asset downloads are
 * private (JWT-authenticated), so an id must be fetched as a blob rather than
 * dropped straight into `src` — a bare <img src> would 401.
 */
function useAssetUrl(ref?: string): string | undefined {
  const [blobUrl, setBlobUrl] = useState<string | undefined>();
  const isId = Boolean(ref && UUID_RE.test(ref));

  useEffect(() => {
    if (!ref || !isId) return;
    let cancelled = false;
    let created: string | undefined;
    (async () => {
      try {
        const resp = await apiClient.get(`/media/${ref}/download/`, { responseType: "blob" });
        if (cancelled) return;
        created = URL.createObjectURL(resp.data);
        setBlobUrl(created);
      } catch {
        /* A missing asset shouldn't break the scene — it just renders without it. */
      }
    })();
    return () => {
      cancelled = true;
      if (created) URL.revokeObjectURL(created);
    };
  }, [ref, isId]);

  if (!ref) return undefined;
  return isId ? blobUrl : ref;
}

function SceneSprite({ assetRef, position }: { assetRef: string; position: string }) {
  const url = useAssetUrl(assetRef);
  if (!url) return null;
  return (
    <img
      src={url}
      alt=""
      style={{
        position: "absolute", bottom: 0, maxHeight: "72%", maxWidth: "40%",
        objectFit: "contain", pointerEvents: "none",
        ...(POSITION_STYLE[position] ?? POSITION_STYLE.centre),
      }}
    />
  );
}

export default function SceneShell({ workflow, instances, fireTransition, transitionPending }: ShellProps) {
  const qc = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const sceneConfig: SceneConfig = workflow.ui_schema?.scene_config ?? {};

  // Default to an in-progress playthrough so "Continue" is the natural landing.
  const firstOpen = instances.find((i) => !i.completed_at) ?? instances[0];
  const listRow = instances.find((i) => i.id === selectedId) ?? firstOpen ?? null;

  // The list payload omits current_form/computed; the player works one
  // playthrough at a time, so fetching that instance's detail is cheap.
  const { data: detail } = useQuery<WorkflowInstance>({
    queryKey: ["instance", listRow?.id],
    queryFn: async () => (await apiClient.get(`/instances/${listRow!.id}/`)).data,
    enabled: Boolean(listRow?.id),
  });
  const playthrough = detail ?? listRow;

  const scene = playthrough ? sceneConfig[playthrough.current_state_name] ?? {} : {};
  const backgroundUrl = useAssetUrl(scene.background);

  const choices: Transition[] = useMemo(() => {
    if (!playthrough) return [];
    return (workflow.transitions ?? []).filter((t) => t.from_state === playthrough.current_state);
  }, [workflow.transitions, playthrough]);

  const startNewGame = async () => {
    const created = await apiClient.post("/instances/", { workflow_definition: workflow.id });
    await qc.invalidateQueries({ queryKey: ["instances", "by-workflow", workflow.id] });
    setSelectedId(created.data.id);
  };

  if (!playthrough) {
    return (
      <div className="card" style={{ textAlign: "center", padding: 40 }}>
        <p className="text-muted" style={{ marginBottom: 14 }}>No playthrough yet.</p>
        <button className="btn-primary" onClick={startNewGame}>Start a new game</button>
      </div>
    );
  }

  const isEnding = Boolean(playthrough.completed_at);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {/* Save-file controls */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <span className="text-xs text-muted">Playthrough:</span>
        <select
          value={playthrough.id}
          onChange={(e) => setSelectedId(e.target.value)}
          style={{ maxWidth: 320, padding: "6px 10px", fontSize: "0.85rem" }}
        >
          {instances.map((i) => (
            <option key={i.id} value={i.id}>
              {i.reference_number}{i.completed_at ? " — ending reached" : ` — ${i.current_state_name}`}
            </option>
          ))}
        </select>
        <button className="btn-secondary btn-sm" onClick={startNewGame}>+ New game</button>
      </div>

      {/* Stage */}
      <div
        style={{
          position: "relative", width: "100%", aspectRatio: "16 / 9",
          minHeight: 360, borderRadius: 12, overflow: "hidden",
          border: "1px solid var(--border)",
          background: backgroundUrl
            ? `center / cover no-repeat url(${backgroundUrl})`
            : "linear-gradient(160deg, #1a1d27, #0d1117)",
        }}
      >
        {(scene.sprites ?? []).map((sprite, i) => (
          <SceneSprite key={`${sprite.asset}-${i}`} assetRef={sprite.asset} position={sprite.position ?? "centre"} />
        ))}

        {/* Scene title — the state name doubles as the scene name */}
        <div style={{
          position: "absolute", top: 12, left: 16, padding: "4px 10px",
          borderRadius: 6, background: "rgba(13,17,23,0.72)",
          fontSize: "0.72rem", letterSpacing: "0.08em", textTransform: "uppercase",
          color: "var(--text-secondary)",
        }}>
          {playthrough.current_state_name}
        </div>

        {/* Dialogue box */}
        <div style={{
          position: "absolute", left: 0, right: 0, bottom: 0,
          padding: "18px 22px 22px",
          background: "linear-gradient(to top, rgba(13,17,23,0.94) 70%, rgba(13,17,23,0))",
        }}>
          {scene.speaker && (
            <div style={{ fontWeight: 700, color: "var(--accent-light)", marginBottom: 4 }}>
              {interpolate(scene.speaker, playthrough)}
            </div>
          )}
          <p style={{ fontSize: "1.02rem", lineHeight: 1.6, minHeight: "1.6em" }}>
            {scene.dialogue
              ? interpolate(scene.dialogue, playthrough)
              : <span className="text-muted">This scene has no dialogue yet.</span>}
          </p>
        </div>
      </div>

      {/* Choices */}
      {isEnding ? (
        <div className="card" style={{ textAlign: "center", padding: 24 }}>
          <div style={{ fontSize: 30 }}>🎬</div>
          <h3 style={{ marginTop: 6 }}>The End — “{playthrough.current_state_name}”</h3>
          <button className="btn-primary btn-sm" style={{ marginTop: 12 }} onClick={startNewGame}>
            Play again
          </button>
        </div>
      ) : (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
          {choices.length === 0 ? (
            <p className="text-muted text-sm">No choices lead onward from this scene.</p>
          ) : (
            choices.map((choice) => (
              <button
                key={choice.id}
                className="btn-secondary"
                disabled={transitionPending}
                onClick={() => fireTransition(playthrough, choice)}
                style={{ flex: "1 1 220px", justifyContent: "flex-start", padding: "12px 16px", textAlign: "left" }}
              >
                {choice.display_name || choice.name}
              </button>
            ))
          )}
        </div>
      )}

      <p className="text-xs text-muted">
        Choices are workflow transitions — rules, approvals and required forms still apply,
        so a locked path stays locked until the story earns it.
      </p>
    </div>
  );
}
