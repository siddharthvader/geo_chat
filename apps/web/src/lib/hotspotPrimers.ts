import type { Hotspot } from "@buildingtalk/shared";

export type HotspotPrimer = {
  id: string;
  name: string;
  overview: string;
  followUps: string[];
};

const PRECOMPUTED: Record<string, { overview: string; followUps: string[] }> = {
  "palace_of_fine_arts:entablature_frieze": {
    overview:
      "The entablature frieze is the horizontal decorative band above the columns. At the Palace of Fine Arts, it reinforces the Beaux-Arts and Roman revival language by visually tying the colonnade together with continuous sculptural detail.",
    followUps: [
      "What motifs appear in the frieze and what do they symbolize?",
      "How does the frieze relate to the Corinthian capitals below it?",
      "Was the frieze reconstructed in the 1960s rebuild, and how faithfully?",
    ],
  },
  "palace_of_fine_arts:dome_coffers": {
    overview:
      "The dome coffers are the recessed ceiling panels inside the rotunda. They reduce perceived mass, create rhythmic light and shadow, and emphasize the monumental interior geometry.",
    followUps: [
      "How do coffers affect acoustics and lighting in the rotunda?",
      "What classical precedents inspired this coffer pattern?",
      "Are these coffers original material or part of reconstruction?",
    ],
  },
  "palace_of_fine_arts:weeping_ladies": {
    overview:
      "The Weeping Ladies are iconic sculptural figures associated with the rotunda composition. They contribute to the site's elegiac mood and its intended ruin-like, romantic atmosphere.",
    followUps: [
      "Who designed the Weeping Ladies and what is their meaning?",
      "Where are they positioned relative to the rotunda axis?",
      "How do they connect to the 1915 exposition themes?",
    ],
  },
  "palace_of_fine_arts:rotunda": {
    overview:
      "The rotunda is the visual and symbolic center of the Palace of Fine Arts. It anchors the lagoon approach and organizes the surrounding colonnade into a ceremonial composition.",
    followUps: [
      "Why did Maybeck center the composition on a rotunda?",
      "How does the rotunda framing change from lagoon to interior views?",
      "What changed between the 1915 structure and the later reconstruction?",
    ],
  },
  "palace_of_fine_arts:ruin_aesthetic_overview": {
    overview:
      "The Palace was deliberately designed to evoke a poetic ruin rather than a purely functional exhibition hall. This aesthetic choice is central to how visitors interpret the site today.",
    followUps: [
      "Why did the designers pursue a ruin aesthetic in 1915?",
      "How did the landscape and lagoon reinforce the ruin effect?",
      "Did the reconstruction preserve that ruin-like intent?",
    ],
  },
  "alcatraz_island:cellhouse_block": {
    overview:
      "The cellhouse block is the core incarceration volume in the Alcatraz model, organized around tightly controlled movement and surveillance logic.",
    followUps: [
      "How did the cellhouse layout support high-security operations?",
      "What changed in this area after the prison closed in 1963?",
      "How does this block compare to other federal penitentiaries of the era?",
    ],
  },
  "alcatraz_island:lighthouse_point": {
    overview:
      "The lighthouse point acts as both a navigational landmark and a visual anchor in the island composition, tying maritime and institutional histories together.",
    followUps: [
      "How old is the Alcatraz lighthouse and what changed over time?",
      "Why is the lighthouse important to visitor orientation today?",
      "How does lighthouse placement relate to the island topography?",
    ],
  },
  "alcatraz_island:dock_arrival_zone": {
    overview:
      "The dock arrival zone frames first contact with Alcatraz, shaping the transition from bay crossing to the island's controlled circulation routes.",
    followUps: [
      "What was the historic arrival process for staff, supplies, and inmates?",
      "How is this zone interpreted differently for modern visitors?",
      "Which structures near the dock are most significant architecturally?",
    ],
  },
};

export function getHotspotPrimer(buildingId: string, hotspot: Hotspot): HotspotPrimer {
  const match = PRECOMPUTED[`${buildingId}:${hotspot.id}`];
  if (match) {
    return {
      id: hotspot.id,
      name: hotspot.name,
      overview: match.overview,
      followUps: match.followUps,
    };
  }

  return {
    id: hotspot.id,
    name: hotspot.name,
    overview: hotspot.description,
    followUps: [
      `What architectural role does ${hotspot.name} play in this building's composition?`,
      `How has ${hotspot.name} changed over time?`,
      `What details should I notice first at ${hotspot.name}?`,
    ],
  };
}

export function buildClientContext(primer: HotspotPrimer): string {
  return [
    `Selected hotspot: ${primer.name} (${primer.id}).`,
    `Overview: ${primer.overview}`,
    `Follow-up hints: ${primer.followUps.join(" | ")}`,
  ].join("\n");
}
