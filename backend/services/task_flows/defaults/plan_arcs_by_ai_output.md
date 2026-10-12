只返回一个符合以下 JSON Schema 的 JSON 对象，不使用代码围栏；不输出正式 ID、祖先、版本、顺序、统计或正文。
{
  "$defs": {
    "ArcCreateV1": {
      "additionalProperties": false,
      "description": "卷下创建篇章时允许提交的内容。",
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
          "$ref": "#/$defs/ArcPlanningV1"
        }
      },
      "required": [
        "title"
      ],
      "title": "ArcCreateV1",
      "type": "object"
    },
    "ArcPlanningV1": {
      "additionalProperties": false,
      "description": "篇章目标、起止状态、节拍和当前小说的实体引用。",
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
      "title": "ArcPlanningV1",
      "type": "object"
    }
  },
  "additionalProperties": false,
  "description": "仅提供篇章可编辑内容，不包含正式 ID 或统计。",
  "properties": {
    "arcs": {
      "items": {
        "$ref": "#/$defs/ArcCreateV1"
      },
      "maxItems": 20,
      "minItems": 1,
      "title": "Arcs",
      "type": "array"
    }
  },
  "required": [
    "arcs"
  ],
  "title": "ArcPlansResultV1",
  "type": "object"
}
