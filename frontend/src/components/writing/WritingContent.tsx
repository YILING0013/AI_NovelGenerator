"use client";

import { useState } from "react";
import type { WritingSidebarItem } from "@/types/novel";
import WritingSidebar from "./WritingSidebar";
import WritingPlaceholder from "./WritingPlaceholder";
import NovelInfoWorkspace from "./novel-info/NovelInfoWorkspace";

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
    return <WritingPlaceholder moduleKey={activeItem} />;
  };

  return (
    <div className="h-[calc(100vh-3.5rem)] flex">
      <WritingSidebar activeItem={activeItem} onSelect={setActiveItem} />
      <div className="flex-1 min-w-0 overflow-hidden flex flex-col">
        {renderMainArea()}
      </div>
    </div>
  );
}
