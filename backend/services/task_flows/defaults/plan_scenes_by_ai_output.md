只返回一个符合以下 JSON Schema 的 JSON 对象，不使用代码围栏；不输出正式 ID、祖先、版本、顺序、统计或正文。
{
  "$defs": {
    "SceneCreateV1": {
      "additionalProperties": false,
      "description": "在当前篇章下创建一个场景。",
      "properties": {
        "title": {
          "maxLength": 120,
          "minLength": 1,
          "title": "Title",
          "type": "string"
        },
        "summary": {
          "default": "",
          "maxLength": 2000,
          "title": "Summary",
          "type": "string"
        },
        "planning": {
          "$ref": "#/$defs/ScenePlanningV1"
        }
      },
      "required": [
        "title"
      ],
      "title": "SceneCreateV1",
      "type": "object"
    },
    "ScenePlanningV1": {
      "additionalProperties": false,
      "description": "场景沿用篇章规划字段，可关联多个地点，不保存正文。",
      "properties": {
        "goal": {
          "default": "",
          "maxLength": 2000,
          "title": "Goal",
          "type": "string"
        },
        "start_state": {
          "default": "",
          "maxLength": 2000,
          "title": "Start State",
          "type": "string"
        },
        "end_state": {
          "default": "",
          "maxLength": 2000,
          "title": "End State",
          "type": "string"
        },
        "key_beats": {
          "items": {
            "maxLength": 2000,
            "type": "string"
          },
          "maxItems": 30,
          "title": "Key Beats",
          "type": "array"
        },
        "continuity_notes": {
          "default": "",
          "maxLength": 2000,
          "title": "Continuity Notes",
          "type": "string"
        },
        "target_chapter_count": {
          "anyOf": [
            {
              "exclusiveMinimum": 0,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Target Chapter Count"
        },
        "target_word_count": {
          "anyOf": [
            {
              "exclusiveMinimum": 0,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Target Word Count"
        },
        "character_ids": {
          "items": {
            "type": "string"
          },
          "maxItems": 50,
          "title": "Character Ids",
          "type": "array"
        },
        "faction_ids": {
          "items": {
            "type": "string"
          },
          "maxItems": 50,
          "title": "Faction Ids",
          "type": "array"
        },
        "location_ids": {
          "items": {
            "type": "string"
          },
          "maxItems": 50,
          "title": "Location Ids",
          "type": "array"
        },
        "item_ids": {
          "items": {
            "type": "string"
          },
          "maxItems": 50,
          "title": "Item Ids",
          "type": "array"
        },
        "rule_ids": {
          "items": {
            "type": "string"
          },
          "maxItems": 50,
          "title": "Rule Ids",
          "type": "array"
        }
      },
      "title": "ScenePlanningV1",
      "type": "object"
    }
  },
  "additionalProperties": false,
  "description": "场景候选不包含正文。",
  "properties": {
    "scenes": {
      "items": {
        "$ref": "#/$defs/SceneCreateV1"
      },
      "maxItems": 20,
      "minItems": 1,
      "title": "Scenes",
      "type": "array"
    }
  },
  "required": [
    "scenes"
  ],
  "title": "ScenePlansResultV1",
  "type": "object"
}
