"use client";

import { Button } from "@heroui/react";

interface StickyActionBarProps {
  children: React.ReactNode;
}

export default function StickyActionBar({ children }: StickyActionBarProps) {
  return (
    <div className="sticky bottom-0 z-10 bg-background/95 backdrop-blur-sm border-t border-border px-6 py-4">
      <div className="flex items-center justify-end gap-3">
        {children}
      </div>
    </div>
  );
}

interface ActionButtonProps {
  label: string;
  onPress: () => void;
  variant?: "primary" | "ghost" | "outline";
  isDisabled?: boolean;
  className?: string;
}

export function ActionButton({
  label,
  onPress,
  variant = "primary",
  isDisabled = false,
  className = "",
}: ActionButtonProps) {
  return (
    <Button
      variant={variant}
      onPress={onPress}
      isDisabled={isDisabled}
      className={
        variant === "primary"
          ? `bg-accent text-white hover:bg-accent-hover ${className}`
          : className
      }
    >
      {label}
    </Button>
  );
}
