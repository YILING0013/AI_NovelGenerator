"use client";

import { useState } from "react";
import type { WritingSidebarItem } from "@/types/novel";
import WritingSidebar from "./WritingSidebar";
import WritingPlaceholder from "./WritingPlaceholder";
import NovelInfoWorkspace from "./novel-info/NovelInfoWorkspace";
import FactionCardsWorkspace from "./factions/FactionCardsWorkspace";

interface WritingContentProps {
  mode: "create" | "edit";
  novelId?: string;
}

export default function WritingContent({ mode, novelId }: WritingContentProps) {
  const [activeItem, setActiveItem] = useState<WritingSidebarItem>("novel-info");

  const renderMainArea = () => {
    if (activeItem === "novel-info") {
      return <NovelInfoWorkspace mode={mode} novelId={novelId} />;
    }
    if (activeItem === "faction-cards") {
      return <FactionCardsWorkspace mode={mode} novelId={novelId} />;
    }
    return <WritingPlaceholder moduleKey={activeItem} />;
  };

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col md:flex-row">
      <WritingSidebar activeItem={activeItem} onSelect={setActiveItem} />
      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        {renderMainArea()}
      </div>
    </div>
  );
}
