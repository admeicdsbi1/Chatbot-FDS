"use client";
import { useEffect, useState } from "react";
import {
  ArrowLeft,
  CircleDot,
  ClipboardList,
  DoorOpen,
  Disc,
  Flame,
  LifeBuoy,
  Snowflake,
  TrainFront,
  Wrench,
  Zap,
} from "lucide-react";
import { fetchSystems } from "@/lib/api";
import type { SystemInfo } from "@/lib/types";

const ICONS: Record<string, typeof Flame> = {
  "clipboard-list": ClipboardList,
  flame: Flame,
  disc: Disc,
  zap: Zap,
  "door-open": DoorOpen,
  snowflake: Snowflake,
  "circle-dot": CircleDot,
  "train-front": TrainFront,
  "life-buoy": LifeBuoy,
};

/** Shown while the backend wakes up (Render free tier can take ~50s from cold).
 *  Same nine areas as backend/catalog.py, without the live counts. */
const FALLBACK: SystemInfo[] = [
  { id: "schedules", label: "Shop Schedules", sublabel: "SS-1 · SS-2 · POH · daily exam", icon: "clipboard-list", chunks: 0, documents: 0, questions: ["What activities are covered in the SS-1 schedule for Vande Bharat?", "Bogie run test procedure after schedule", "Daily safety examination items for mechanical equipment"] },
  { id: "fire", label: "Fire Detection & Suppression", sublabel: "FSDS · FDSS · aerosol · LHD", icon: "flame", chunks: 0, documents: 0, questions: ["FSDS system me MCB ki rating kitni honi chahiye?", "Smoke test procedure for FSDS", "Aerosol generator pin removal guidelines"] },
  { id: "wsp", label: "Wheel Slide Protection", sublabel: "WSP · dump valves · brakes", icon: "disc", chunks: 0, documents: 0, questions: ["WSP self test procedure", "Dump valve air gap setting", "WSP fault codes for Faiveley AEF G2"] },
  { id: "electrical", label: "Electrical & TCMS", sublabel: "VB/SMI/E series · VCB · connectors", icon: "zap", chunks: 0, documents: 0, questions: ["VCB isolation procedure in Vande Bharat trainset", "Cycle check inspection of jumper cables", "Torque value for inter-vehicle coupler"] },
  { id: "interiors", label: "Doors & Interiors", sublabel: "CAI series · FRP · seats · panels", icon: "door-open", chunks: 0, documents: 0, questions: ["Nosecone sealing work in DTC of Vande Bharat", "FRP panel rectification and cleaning procedure", "Automatic door troubleshooting steps"] },
  { id: "hvac", label: "HVAC", sublabel: "RMPU · air ducts · cooling", icon: "snowflake", chunks: 0, documents: 0, questions: ["Modified supply and return air ducts in Vande Bharat", "RMPU maintenance schedule", "HVAC filter cleaning interval"] },
  { id: "running-gear", label: "Wheels & Bearings", sublabel: "CTRB · wheel profile · axle", icon: "circle-dot", chunks: 0, documents: 0, questions: ["CTRB refurbishment interval for Vande Bharat", "Wheel condemning diameter limit", "Wheel re-profiling criteria"] },
  { id: "bogie", label: "Bogie & Air Suspension", sublabel: "springs · dampers · ASDIS", icon: "train-front", chunks: 0, documents: 0, questions: ["Stabilizer bar torque value", "Vibration in Vande Bharat coaches after SS-1", "Air suspension levelling valve link length"] },
  { id: "enroute", label: "En-route Troubleshooting", sublabel: "failures in section · quick isolation", icon: "life-buoy", chunks: 0, documents: 0, questions: ["Isolation procedure for parking brake en-route", "What to do if brakes do not release in section?", "Master controller malfunctioning troubleshooting"] },
];

export default function SystemGrid({ onPick }: { onPick: (q: string) => void }) {
  const [systems, setSystems] = useState<SystemInfo[]>(FALLBACK);
  const [live, setLive] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    fetchSystems().then((s) => {
      if (alive && s.length) {
        setSystems(s);
        setLive(true);
      }
    });
    return () => {
      alive = false;
    };
  }, []);

  const open = systems.find((s) => s.id === openId);

  if (open) {
    const Icon = ICONS[open.icon] || Wrench;
    return (
      <div className="mx-auto w-full max-w-reading px-4 py-6">
        <button
          type="button"
          onClick={() => setOpenId(null)}
          className="mb-3 inline-flex min-h-[40px] items-center gap-1.5 rounded-lg px-2 text-[0.82rem] font-medium text-ink-dim transition hover:text-accent"
        >
          <ArrowLeft size={15} aria-hidden /> All areas
        </button>
        <div className="mb-4 flex items-start gap-3">
          <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-accent/12 text-accent">
            <Icon size={20} aria-hidden />
          </span>
          <div>
            <h2 className="text-base font-bold text-ink">{open.label}</h2>
            <p className="text-[0.8rem] text-ink-dim">
              {open.sublabel}
              {live && open.documents > 0 && (
                <> · {open.documents} document{open.documents === 1 ? "" : "s"}</>
              )}
            </p>
          </div>
        </div>
        <ul className="flex flex-col gap-2">
          {open.questions.map((q) => (
            <li key={q}>
              <button
                type="button"
                onClick={() => onPick(q)}
                className="w-full rounded-xl border border-line/15 bg-bg-card px-3.5 py-3 text-left text-[0.9rem] leading-snug text-ink transition hover:border-accent/50 hover:bg-accent/5 active:scale-[0.995]"
              >
                {q}
              </button>
            </li>
          ))}
        </ul>
        <p className="mt-4 text-center text-[0.8rem] text-ink-dim">
          Or type your own question below.
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-reading px-4 py-6">
      <div className="mb-5 text-center">
        <h2 className="text-lg font-bold text-ink">What are you working on?</h2>
        <p className="mx-auto mt-1 max-w-md text-[0.88rem] leading-snug text-ink-dim">
          Pick an area, or just ask — in English, Hindi or Hinglish. Tap the mic
          if your hands are busy.
        </p>
      </div>
      <ul className="grid grid-cols-1 gap-2 min-[380px]:grid-cols-2 lg:grid-cols-3">
        {systems.map((s) => {
          const Icon = ICONS[s.icon] || Wrench;
          return (
            <li key={s.id}>
              <button
                type="button"
                onClick={() => setOpenId(s.id)}
                className="flex h-full w-full flex-col gap-1.5 rounded-xl border border-line/15 bg-bg-card p-3 text-left transition hover:border-accent/50 hover:bg-accent/5 active:scale-[0.99]"
              >
                <span className="grid h-9 w-9 place-items-center rounded-lg bg-accent/12 text-accent">
                  <Icon size={17} aria-hidden />
                </span>
                <span className="text-[0.85rem] font-semibold leading-tight text-ink">
                  {s.label}
                </span>
                <span className="text-[0.72rem] leading-tight text-ink-faint">
                  {s.sublabel}
                </span>
                {live && s.documents > 0 && (
                  <span className="mt-auto pt-1 text-[0.7rem] font-medium text-ink-faint">
                    {s.documents} doc{s.documents === 1 ? "" : "s"}
                  </span>
                )}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
