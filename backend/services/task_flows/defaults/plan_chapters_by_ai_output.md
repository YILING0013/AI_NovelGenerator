只返回一个符合以下 JSON Schema 的 JSON 对象，不使用代码围栏；不输出正式 ID、祖先、版本、顺序、统计或正文。
{
  "$defs": {
    "ChapterPlanCandidateV1": {
      "additionalProperties": false,
      "description": "章计划生成只提供规划，正式新章正文由服务置空。",
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
          "$ref": "#/$defs/ChapterPlanV2"
        }
      },
      "required": [
        "title"
      ],
      "title": "ChapterPlanCandidateV1",
      "type": "object"
    },
    "ChapterPlanV2": {
      "additionalProperties": false,
      "description": "当前章节计划；正文单独保存，人物视角可暂不选择。",
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
        "beats": {
          "items": {
            "maxLength": 2000,
            "type": "string"
          },
          "maxItems": 30,
          "title": "Beats",
          "type": "array"
        },
        "pov_character_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Pov Character Id"
        },
        "must_include": {
          "items": {
            "maxLength": 2000,
            "type": "string"
          },
          "maxItems": 30,
          "title": "Must Include",
          "type": "array"
        },
        "must_avoid": {
          "items": {
            "maxLength": 2000,
            "type": "string"
          },
          "maxItems": 30,
          "title": "Must Avoid",
          "type": "array"
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
        }
      },
      "title": "ChapterPlanV2",
      "type": "object"
    }
  },
  "additionalProperties": false,
  "description": "场景内有序的章计划候选。",
  "properties": {
    "chapters": {
      "items": {
        "$ref": "#/$defs/ChapterPlanCandidateV1"
      },
      "maxItems": 20,
      "minItems": 1,
      "title": "Chapters",
      "type": "array"
    }
  },
  "required": [
    "chapters"
  ],
  "title": "ChapterPlansResultV1",
  "type": "object"
}
