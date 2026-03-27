"use client";

import { useTranslations } from "next-intl";
import { Card, TextField, Input, Label, NumberField } from "@heroui/react";
import type { AppConfig } from "@/types/config";

interface Props {
  config: AppConfig;
  onChange: (partial: Partial<AppConfig>) => void;
}

export function DatabaseCard({ config, onChange }: Props) {
  const t = useTranslations("settings.database");

  return (
    <Card className="bg-surface border border-border shadow-sm">
      <Card.Header>
        <Card.Title className="text-lg font-semibold text-foreground">{t("title")}</Card.Title>
      </Card.Header>
      <Card.Content className="space-y-4">
        <TextField
          value={config.mongodb_url || ""}
          onChange={(v) => onChange({ mongodb_url: v })}
          isRequired
          variant="primary"
        >
          <Label>{t("mongodbUrl")}</Label>
          <Input placeholder={t("mongodbUrlPlaceholder")} className="border-border" />
        </TextField>

        <TextField
          value={config.mongo_database_name || ""}
          onChange={(v) => onChange({ mongo_database_name: v })}
          isRequired
          variant="primary"
        >
          <Label>{t("databaseName")}</Label>
          <Input placeholder={t("databaseNamePlaceholder")} className="border-border" />
        </TextField>

        <NumberField
          value={config.mongo_timeout_ms ?? 5000}
          onChange={(v) => onChange({ mongo_timeout_ms: Math.max(0, v) })}
          minValue={0}
        >
          <Label>{t("timeoutMs")}</Label>
          <NumberField.Group>
            <NumberField.DecrementButton />
            <NumberField.Input className="border-border" />
            <NumberField.IncrementButton />
          </NumberField.Group>
        </NumberField>
      </Card.Content>
    </Card>
  );
}
