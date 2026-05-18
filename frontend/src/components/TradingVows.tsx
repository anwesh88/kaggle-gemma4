"use client";
import { useState } from "react";
import { api } from "@/lib/api";

const DEFAULT_VOWS = [
  "I will stop trading after 2 consecutive losses",
  "I will not use more than 50% of my margin",
  "I will not revenge trade after a big loss",
];

export function TradingVows() {
  const [vows,    setVows]    = useState<string[]>(DEFAULT_VOWS);
  const [newVow,  setNewVow]  = useState("");
  const [editing, setEditing] = useState(false);
  const [saved,   setSaved]   = useState(false);
  const [saving,  setSaving]  = useState(false);

  async function handleAdd() {
    if (!newVow.trim()) return;
    setVows(prev => [...prev, newVow.trim()]);
    setNewVow("");
  }

  function handleRemove(i: number) {
    setVows(prev => prev.filter((_, j) => j !== i));
  }

  async function handleDone() {
    setSaving(true);
    try {
      await api.updateVows(vows);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      console.error("Failed to save vows:", e);
    } finally {
      setSaving(false);
      setEditing(false);
    }
  }

  const inputStyle: React.CSSProperties = {
    flex: 1,
    padding: "8px 11px",
    border: "1px solid #D0CCC4",
    borderRadius: "8px",
    background: "#F9F8F6",
    color: "#1A1814",
    fontSize: "12px",
    outline: "none",
    transition: "border-color 0.15s",
  };

  return (
    <div style={{
      background: "#ffffff",
      borderRadius: "12px",
      border: "1px solid #E8E5DF",
      overflow: "hidden",
    }}>
      {/* Header */}
      <div style={{
        padding: "11px 16px",
        borderBottom: "1px solid #E8E5DF",
        display: "flex", alignItems: "center", gap: "8px",
      }}>
        <div style={{
          width: "28px", height: "28px", borderRadius: "7px", flexShrink: 0,
          background: "#FFF7ED", border: "1px solid #FED7AA",
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
            stroke="#F97316" strokeWidth="2.5" strokeLinecap="round">
            <polyline points="20 6 9 17 4 12"/>
          </svg>
        </div>
        <span style={{
          fontSize: "11px", fontWeight: "700", color: "#1A1814",
          textTransform: "uppercase", letterSpacing: "0.07em",
        }}>
          Trading Vows
        </span>
        <span style={{
          marginLeft: "auto", fontSize: "10px", color: "#9B9890",
          fontStyle: "italic",
        }}>
          Identity Contract
        </span>
      </div>

      <div style={{ padding: "14px 16px", display: "flex", flexDirection: "column", gap: "10px" }}>

        {/* Vow list */}
        <div style={{
          display: "flex", flexDirection: "column", gap: "6px",
          maxHeight: "180px", overflowY: "auto",
        }}>
          {vows.map((vow, i) => (
            <div key={i} style={{
              display: "flex", alignItems: "flex-start", gap: "8px",
              padding: "8px 10px",
              borderRadius: "8px",
              background: "#F9F8F6",
              border: "1px solid #E8E5DF",
            }}>
              {/* Bullet */}
              <div style={{
                width: "6px", height: "6px", borderRadius: "50%",
                background: "#F97316", flexShrink: 0, marginTop: "5px",
              }} />

              <p style={{
                flex: 1, fontSize: "12px", color: "#1A1814", lineHeight: "1.5",
              }}>
                {vow}
              </p>

              {/* Remove button — only in edit mode */}
              {editing && (
                <button
                  onClick={() => handleRemove(i)}
                  style={{
                    flexShrink: 0, width: "18px", height: "18px",
                    border: "none", background: "transparent",
                    cursor: "pointer", color: "#C8C5BE",
                    display: "flex", alignItems: "center", justifyContent: "center",
                    borderRadius: "4px", transition: "color 0.15s",
                    marginTop: "1px",
                    fontSize: "16px", lineHeight: "1",
                  }}
                  onMouseEnter={e => (e.currentTarget.style.color = "#DC2626")}
                  onMouseLeave={e => (e.currentTarget.style.color = "#C8C5BE")}
                  title="Remove vow"
                >
                  ×
                </button>
              )}
            </div>
          ))}
        </div>

        {/* Add vow row — only in edit mode */}
        {editing && (
          <div style={{ display: "flex", gap: "8px" }}>
            <input
              type="text"
              value={newVow}
              onChange={e => setNewVow(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleAdd()}
              placeholder="Add a new vow…"
              style={inputStyle}
            />
            <button
              onClick={handleAdd}
              disabled={!newVow.trim()}
              style={{
                width: "34px", height: "34px", borderRadius: "8px",
                border: "none", flexShrink: 0,
                background: newVow.trim() ? "#F97316" : "#E8E5DF",
                color: newVow.trim() ? "#ffffff" : "#9B9890",
                cursor: newVow.trim() ? "pointer" : "not-allowed",
                display: "flex", alignItems: "center", justifyContent: "center",
                transition: "all 0.15s",
                fontSize: "20px", lineHeight: "1",
              }}
            >
              +
            </button>
          </div>
        )}

        {/* Save confirmation */}
        {saved && (
          <div style={{
            display: "flex", alignItems: "center", gap: "6px",
            padding: "7px 10px", borderRadius: "8px",
            background: "#F0FDF4", border: "1px solid #BBF7D0",
          }}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
              stroke="#16A34A" strokeWidth="2.5" strokeLinecap="round">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
            <span style={{ fontSize: "12px", color: "#16A34A", fontWeight: "600" }}>
              Vows saved — Fin AI will check these on next analysis
            </span>
          </div>
        )}

        {/* Edit / Done button */}
        <button
          onClick={editing ? handleDone : () => setEditing(true)}
          disabled={saving}
          style={{
            width: "100%", padding: "10px",
            borderRadius: "8px",
            background: editing ? "#F97316" : "#FFF7ED",
            color: editing ? "#ffffff" : "#C2410C",
            fontSize: "12px", fontWeight: "700",
            cursor: saving ? "not-allowed" : "pointer",
            transition: "all 0.15s",
            border: editing ? "none" : "1px solid #FED7AA",
            opacity: saving ? 0.7 : 1,
          } as React.CSSProperties}
          onMouseEnter={e => {
            if (!saving) e.currentTarget.style.opacity = "0.88";
          }}
          onMouseLeave={e => {
            e.currentTarget.style.opacity = "1";
          }}
        >
          {saving ? "Saving…" : editing ? "Save Identity Contract" : "Edit Vows"}
        </button>
      </div>
    </div>
  );
}
