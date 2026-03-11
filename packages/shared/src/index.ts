export type ChatRequest = {
  session_id: string;
  message: string;
  building_id?: string;
  client_context?: string;
};

export type Citation = {
  title: string;
  url: string;
  snippet: string;
};

export type HotspotAction = {
  id: string;
  confidence: number;
  reason?: string;
};

export type ChatResponse = {
  answer: string;
  citations: Citation[];
  actions: {
    hotspots: HotspotAction[];
  };
};

export type Hotspot = {
  id: string;
  name: string;
  description: string;
  tags: string[];
  bbox?: {
    min: [number, number, number];
    max: [number, number, number];
  };
  camera?: {
    position: [number, number, number];
    target: [number, number, number];
    fov: number;
  };
  meshNames?: string[];
  priority: number;
};

export type Building = {
  id: string;
  name: string;
  location: string;
  description: string;
  modelUrl: string;
  suggestedPrompts: string[];
  modelAttribution?: string;
  modelSourceUrl?: string;
  modelLicense?: string;
};
