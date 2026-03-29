"""
?⑦넧濡쒖? ?앹꽦 ?쒕퉬??
API 1: 臾몄꽌 ?댁슜??遺꾩꽍???ы쉶 ?쒕??덉씠?섏뿉 留욌뒗 ?뷀꽣??愿怨???낆쓣 ?앹꽦?쒕떎.
"""

import json
from typing import Dict, Any, List, Optional
from ..prompts import get_prompt, render_prompt
from ..utils.llm_client import LLMClient


# ?⑦넧濡쒖? ?앹꽦???꾪븳 ?쒖뒪???꾨＼?꾪듃
ONTOLOGY_SYSTEM_PROMPT = """?덈뒗 吏??洹몃옒???⑦넧濡쒖? ?ㅺ퀎 ?꾨Ц媛??
二쇱뼱吏?臾몄꽌 ?댁슜怨??쒕??덉씠???붽뎄?ы빆??諛뷀깢?쇰줈 **?뚯뀥 誘몃뵒???щ줎 ?쒕??덉씠??*??留욌뒗
?뷀꽣????낃낵 愿怨???낆쓣 ?ㅺ퀎?섎씪.

以묒슂:
- 諛섎뱶??**?좏슚??JSON留?* 異쒕젰?쒕떎.
- JSON ???띿뒪?몃뒗 ?덈? 異쒕젰?섏? ?딅뒗??

## ?묒뾽 諛곌꼍

?곕━???뚯뀥 誘몃뵒???щ줎 ?쒕??덉씠???쒖뒪?쒖쓣 援ъ텞?쒕떎.
???쒖뒪?쒖뿉???뷀꽣?곕뒗 ?ㅼ젣濡?諛쒗솕/?곹샇?묒슜/?뺣낫 ?뺤궛??媛?ν븳 二쇱껜?ъ빞 ?쒕떎.

?뷀꽣???덉떆(?덉슜):
- 媛쒖씤(怨듭씤, ?뱀궗?? ?꾨Ц媛, ?쇰컲 ?ъ슜????
- 湲곗뾽/湲곌?/?⑥껜(怨듭떇 怨꾩젙 ?ы븿)
- ?뺣? 遺泥?洹쒖젣湲곌?
- ?몃줎???뚮옯??
- ?뱀젙 吏묐떒 ????щ뜡, ?숇Ц?? ?쒕??⑥껜 ??

?뷀꽣???덉떆(湲덉?):
- 異붿긽 媛쒕뀗(?щ줎, 媛먯젙, 異붿꽭 ??
- 二쇱젣/?댁뒋(援먯쑁 媛쒗쁺, ?숈닠 ?ㅻ━ ??
- ?쒕룄 ?먯껜(李ъ꽦 吏꾩쁺, 諛섎? 吏꾩쁺 ??

## 異쒕젰 ?뺤떇

?꾨옒 援ъ“瑜?媛吏?JSON?쇰줈 異쒕젰:

```json
{
  "entity_types": [
    {
      "name": "EntityTypeName (?곷Ц PascalCase)",
      "description": "?곷Ц ?ㅻ챸(100???대궡)",
      "attributes": [
        {
          "name": "attribute_name (?곷Ц snake_case)",
          "type": "text",
          "description": "?띿꽦 ?ㅻ챸"
        }
      ],
      "examples": ["example1", "example2"]
    }
  ],
  "edge_types": [
    {
      "name": "RELATION_NAME (?곷Ц UPPER_SNAKE_CASE)",
      "description": "?곷Ц ?ㅻ챸(100???대궡)",
      "source_targets": [
        {"source": "SourceEntityType", "target": "TargetEntityType"}
      ],
      "attributes": []
    }
  ],
  "analysis_summary": "臾몄꽌 ?듭떖 遺꾩꽍 ?붿빟"
}
```

## ?ㅺ퀎 洹쒖튃 (諛섎뱶??以??

1) ?뷀꽣?????
- ?뺥솗??**10媛?*瑜?異쒕젰?쒕떎.
- 留덉?留?2媛쒕뒗 諛섎뱶??fallback ???
  - `Person`
  - `Organization`
- ??8媛쒕뒗 臾몄꽌 留λ씫 湲곕컲??援ъ껜 ??낆쑝濡??ㅺ퀎?쒕떎.

2) 愿怨????
- 6~10媛쒕줈 ?ㅺ퀎?쒕떎.
- ?ㅼ젣 ?뚯뀥 ?곹샇?묒슜(?곹뼢, ?멸툒, 諛섏쓳, ?묒뾽, ?由?????諛섏쁺?쒕떎.
- `source_targets`媛 ?뺤쓽???뷀꽣????낅뱾??異⑸텇???ш큵?댁빞 ?쒕떎.

3) ?띿꽦 ???
- ?뷀꽣????낅떦 1~3媛??듭떖 ?띿꽦留??뺤쓽?쒕떎.
- ?덉빟?대뒗 ?띿꽦紐낆쑝濡??ъ슜 湲덉?:
  `name`, `uuid`, `group_id`, `created_at`, `summary`
- 沅뚯옣 ?덉떆:
  `full_name`, `title`, `role`, `position`, `location`, `description`
"""

ONTOLOGY_SYSTEM_PROMPT = get_prompt("ontology.system")


class OntologyGenerator:
    """
    ?⑦넧濡쒖? ?앹꽦湲?
    臾몄꽌 ?댁슜??遺꾩꽍???뷀꽣??愿怨?????뺤쓽瑜??앹꽦?쒕떎.
    """
    
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or LLMClient()
    
    def generate(
        self,
        document_texts: List[str],
        simulation_requirement: str,
        additional_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        ?⑦넧濡쒖? ?뺤쓽瑜??앹꽦?쒕떎.

        Args:
            document_texts: 臾몄꽌 ?띿뒪??紐⑸줉
            simulation_requirement: ?쒕??덉씠???붽뎄?ы빆
            additional_context: 異붽? 而⑦뀓?ㅽ듃

        Returns:
            ?⑦넧濡쒖? ?뺤쓽(`entity_types`, `edge_types` ??
        """
        # ?ъ슜??硫붿떆吏 援ъ꽦
        user_message = self._build_user_message(
            document_texts, 
            simulation_requirement,
            additional_context
        )
        
        messages = [
            {"role": "system", "content": ONTOLOGY_SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ]
        
        # LLM ?몄텧
        result = self.llm_client.chat_json(
            messages=messages,
            temperature=0.3,
            max_tokens=4096
        )
        
        # 寃利?諛??꾩쿂由?
        result = self._validate_and_process(result)
        
        return result
    
    # LLM???꾨떖???띿뒪??理쒕? 湲몄씠(5留뚯옄)
    MAX_TEXT_LENGTH_FOR_LLM = 50000
    
    def _build_user_message(
        self,
        document_texts: List[str],
        simulation_requirement: str,
        additional_context: Optional[str]
    ) -> str:
        """Build the ontology prompt payload from the shared prompt registry."""

        combined_text = "\n\n---\n\n".join(document_texts)
        original_length = len(combined_text)

        rendered_text = combined_text
        if len(rendered_text) > self.MAX_TEXT_LENGTH_FOR_LLM:
            rendered_text = rendered_text[:self.MAX_TEXT_LENGTH_FOR_LLM]
            rendered_text += (
                f"\n\n...(original length: {original_length} chars, "
                f"truncated to {self.MAX_TEXT_LENGTH_FOR_LLM} chars for the LLM)..."
            )

        additional_context_block = ""
        if additional_context:
            additional_context_block = f"\n\n## Additional Context\n\n{additional_context}"

        return render_prompt(
            "ontology.user_template",
            simulation_requirement=simulation_requirement,
            combined_text=rendered_text,
            additional_context_block=additional_context_block,
        )

    def _validate_and_process(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """寃곌낵瑜?寃利앺븯怨??꾩쿂由ы븳??"""
        
        # ?꾩닔 ?꾨뱶 蹂댁옣
        if "entity_types" not in result:
            result["entity_types"] = []
        if "edge_types" not in result:
            result["edge_types"] = []
        if "analysis_summary" not in result:
            result["analysis_summary"] = ""
        
        # ?뷀꽣?????寃利?
        for entity in result["entity_types"]:
            if "attributes" not in entity:
                entity["attributes"] = []
            if "examples" not in entity:
                entity["examples"] = []
            # description 湲몄씠 ?쒗븳(100??
            if len(entity.get("description", "")) > 100:
                entity["description"] = entity["description"][:97] + "..."
        
        # 愿怨????寃利?
        for edge in result["edge_types"]:
            if "source_targets" not in edge:
                edge["source_targets"] = []
            if "attributes" not in edge:
                edge["attributes"] = []
            if len(edge.get("description", "")) > 100:
                edge["description"] = edge["description"][:97] + "..."
        
        # Zep API ?쒗븳: 而ㅼ뒪? ?뷀꽣???ｌ? ???媛곴컖 理쒕? 10媛?
        MAX_ENTITY_TYPES = 10
        MAX_EDGE_TYPES = 10
        
        # fallback ????뺤쓽
        person_fallback = {
            "name": "Person",
            "description": "Any individual person not fitting other specific person types.",
            "attributes": [
                {"name": "full_name", "type": "text", "description": "Full name of the person"},
                {"name": "role", "type": "text", "description": "Role or occupation"}
            ],
            "examples": ["ordinary citizen", "anonymous netizen"]
        }
        
        organization_fallback = {
            "name": "Organization",
            "description": "Any organization not fitting other specific organization types.",
            "attributes": [
                {"name": "org_name", "type": "text", "description": "Name of the organization"},
                {"name": "org_type", "type": "text", "description": "Type of organization"}
            ],
            "examples": ["small business", "community group"]
        }
        
        # fallback ???議댁옱 ?щ? ?뺤씤
        entity_names = {e["name"] for e in result["entity_types"]}
        has_person = "Person" in entity_names
        has_organization = "Organization" in entity_names
        
        # 異붽???fallback ???紐⑸줉
        fallbacks_to_add = []
        if not has_person:
            fallbacks_to_add.append(person_fallback)
        if not has_organization:
            fallbacks_to_add.append(organization_fallback)
        
        if fallbacks_to_add:
            current_count = len(result["entity_types"])
            needed_slots = len(fallbacks_to_add)
            
            # 異붽? ??10媛쒕? ?섏쑝硫?湲곗〈 ????쇰? ?쒓굅
            if current_count + needed_slots > MAX_ENTITY_TYPES:
                # ?쒓굅 ???媛쒖닔 怨꾩궛
                to_remove = current_count + needed_slots - MAX_ENTITY_TYPES
                # ?ㅼ뿉???쒓굅(?욎そ??以묒슂??援ъ껜 ????곗꽑 蹂댁〈)
                result["entity_types"] = result["entity_types"][:-to_remove]
            
            # fallback ???異붽?
            result["entity_types"].extend(fallbacks_to_add)
        
        # 理쒖쥌 ?쒗븳 ?ы솗??諛⑹뼱??泥섎━)
        if len(result["entity_types"]) > MAX_ENTITY_TYPES:
            result["entity_types"] = result["entity_types"][:MAX_ENTITY_TYPES]
        
        if len(result["edge_types"]) > MAX_EDGE_TYPES:
            result["edge_types"] = result["edge_types"][:MAX_EDGE_TYPES]
        
        return result
    
    def generate_python_code(self, ontology: Dict[str, Any]) -> str:
        """
        ?⑦넧濡쒖? ?뺤쓽瑜?Python 肄붾뱶(ontology.py ?좎궗 ?뺥깭)濡?蹂?섑븳??

        Args:
            ontology: ?⑦넧濡쒖? ?뺤쓽

        Returns:
            Python 肄붾뱶 臾몄옄??
        """
        code_lines = [
            '"""',
            'Custom entity type definitions',
            'Auto-generated by MiroFish for social opinion simulation',
            '"""',
            '',
            'from pydantic import Field',
            'from zep_cloud.external_clients.ontology import EntityModel, EntityText, EdgeModel',
            '',
            '',
            '# ============== Entity Type Definitions ==============',
            '',
        ]
        
        # ?뷀꽣?????肄붾뱶 ?앹꽦
        for entity in ontology.get("entity_types", []):
            name = entity["name"]
            desc = entity.get("description", f"A {name} entity.")
            
            code_lines.append(f'class {name}(EntityModel):')
            code_lines.append(f'    """{desc}"""')
            
            attrs = entity.get("attributes", [])
            if attrs:
                for attr in attrs:
                    attr_name = attr["name"]
                    attr_desc = attr.get("description", attr_name)
                    code_lines.append(f'    {attr_name}: EntityText = Field(')
                    code_lines.append(f'        description="{attr_desc}",')
                    code_lines.append(f'        default=None')
                    code_lines.append(f'    )')
            else:
                code_lines.append('    pass')
            
            code_lines.append('')
            code_lines.append('')
        
        code_lines.append('# ============== Relation Type Definitions ==============')
        code_lines.append('')
        
        # 愿怨????肄붾뱶 ?앹꽦
        for edge in ontology.get("edge_types", []):
            name = edge["name"]
            # PascalCase ?대옒?ㅻ챸?쇰줈 蹂??
            class_name = ''.join(word.capitalize() for word in name.split('_'))
            desc = edge.get("description", f"A {name} relationship.")
            
            code_lines.append(f'class {class_name}(EdgeModel):')
            code_lines.append(f'    """{desc}"""')
            
            attrs = edge.get("attributes", [])
            if attrs:
                for attr in attrs:
                    attr_name = attr["name"]
                    attr_desc = attr.get("description", attr_name)
                    code_lines.append(f'    {attr_name}: EntityText = Field(')
                    code_lines.append(f'        description="{attr_desc}",')
                    code_lines.append(f'        default=None')
                    code_lines.append(f'    )')
            else:
                code_lines.append('    pass')
            
            code_lines.append('')
            code_lines.append('')
        
        # ????뺤뀛?덈━ ?앹꽦
        code_lines.append('# ============== Type Config ==============')
        code_lines.append('')
        code_lines.append('ENTITY_TYPES = {')
        for entity in ontology.get("entity_types", []):
            name = entity["name"]
            code_lines.append(f'    "{name}": {name},')
        code_lines.append('}')
        code_lines.append('')
        code_lines.append('EDGE_TYPES = {')
        for edge in ontology.get("edge_types", []):
            name = edge["name"]
            class_name = ''.join(word.capitalize() for word in name.split('_'))
            code_lines.append(f'    "{name}": {class_name},')
        code_lines.append('}')
        code_lines.append('')
        
        # ?ｌ? source_targets 留ㅽ븨 ?앹꽦
        code_lines.append('EDGE_SOURCE_TARGETS = {')
        for edge in ontology.get("edge_types", []):
            name = edge["name"]
            source_targets = edge.get("source_targets", [])
            if source_targets:
                st_list = ', '.join([
                    f'{{"source": "{st.get("source", "Entity")}", "target": "{st.get("target", "Entity")}"}}'
                    for st in source_targets
                ])
                code_lines.append(f'    "{name}": [{st_list}],')
        code_lines.append('}')
        
        return '\n'.join(code_lines)

