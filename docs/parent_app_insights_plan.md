# Plan: Parent App — Child Discoveries / Insights (Profile Details)

## 1. Goal

Build a **Child Discoveries / Insights** section that lives on the **child’s Profile Details** page. It is **per child**, not per conversation, and is **always present** (above the “Recent Conversations” section).

The section should:

- Communicate **what the child has explored** and **what the child has demonstrated** (across all relevant sessions).
- Be **grouped by framework/category** (e.g. Social Emotional Learning, Developmental Growth).
- Use **clear, friendly wording** and **parent-facing labels**.
- Avoid the feel of a **formal test report**.

Tone should feel like a **summary of this child’s journey so far**, not “Assessment results” or “Today’s session.” Per-conversation insights may be added later.

---

## 2. Architecture: parent app uses jubu_datastore only

**The parent app talks only to jubu_datastore.** It does **not** talk to jubu_backend. jubu_backend and jubu_parent_app do not communicate with each other.

The parent app has **user_id** and **child_id** (e.g. from the profile being viewed). It gets **all** information needed for the Insights section by calling **jubu_datastore** directly (as a dependency / shared library):

- **Capability state** for the child → `CapabilityDatastore.get_child_capability_state(child_id)`
- **Item labels and definitions** → `CapabilityDefinitionRegistry.get_item(item_id)` (registry from `load_default_registry()` or equivalent)

The parent app (or a thin data layer inside it) builds the structure for the UI from these APIs. No backend API or HTTP call to jubu_backend is involved.

---

## 3. Data shape for the UI (build this in the parent app from datastore)

Use the following structure when rendering the Insights section. The parent app **builds** this from jubu_datastore; nothing “sends” it from a backend.

**Per child, you have:**

- **child_id**, **child_name** (child_name comes from profile data, which the parent app also gets from jubu_datastore / profile APIs).
- **State by framework:** `CapabilityDatastore.get_child_capability_state(child_id)` → `Dict[framework_id, List[ChildCapabilityState]]`. Each state has `item_id`, `current_status` (`"demonstrated"` | `"emerging"` | `"not_observed"`).
- **Labels:** For each `item_id`, `CapabilityDefinitionRegistry.get_item(item_id)` → `CapabilityItemDefinition` with `parent_friendly_label`, etc.
- **Framework display names:** Map `framework_id` to a friendly name (e.g. in the parent app or a small shared constant):
  - `casel` → **“Social Emotional Learning”**
  - `developmental_milestones` → **“Developmental Growth”**

**Suggested in-memory shape** (build this in the parent app from the above):

```json
{
  "child_id": "uuid",
  "child_name": "Lucy",
  "summary_sentence": "Lucy has shown curiosity about animals, recognizes feelings in stories, and joins imaginative play.",
  "frameworks": [
    {
      "framework_id": "casel",
      "framework_display_name": "Social Emotional Learning",
      "items": [
        {
          "item_id": "casel.self_awareness.identify_basic_emotions",
          "parent_friendly_label": "Recognizes feelings",
          "status": "demonstrated"
        },
        {
          "item_id": "casel.social_awareness.show_empathy",
          "parent_friendly_label": "Shows empathy",
          "status": "emerging"
        }
      ]
    },
    {
      "framework_id": "developmental_milestones",
      "framework_display_name": "Developmental Growth",
      "items": [ ... ]
    }
  ],
  "suggested_next_activity": null
}
```

- **status** = state’s `current_status`: `"demonstrated"` | `"emerging"` | `"not_observed"`.
- **summary_sentence** = build in the parent app from item labels and statuses (e.g. simple template: “{child_name} has shown …” for demonstrated/emerging items), or leave as placeholder until you add logic.
- **suggested_next_activity** = optional; can be `null` for now.

---

## 4. How to get the data (jubu_datastore APIs)

**1. Capability state (per child)**  
- Use **CapabilityDatastore** (e.g. from `DatastoreFactory.create_capability_datastore()` or your app’s datastore setup).  
- Call **`get_child_capability_state(child_id)`**.  
- Returns: `Dict[str, List[ChildCapabilityState]]` — keys are `framework_id`, values are lists of state objects. Each state has `item_id`, `current_status`, `framework`, `domain`, `subdomain`, etc.

**2. Item labels (parent_friendly_label)**  
- Use **CapabilityDefinitionRegistry** (e.g. **`load_default_registry(definition_root_path)`** at app startup, or your app’s way of loading definitions).  
- For each `item_id` in the state lists, call **`registry.get_item(item_id)`** to get **CapabilityItemDefinition**.  
- Use **`item.parent_friendly_label`** for the row label. Optionally use **`item.display.priority`** or **`item.display.badge_icon`** for ordering or icons.

**3. Framework display names**  
- Keep a small mapping in the parent app (or in a shared constants module):  
  - `casel` → `"Social Emotional Learning"`  
  - `developmental_milestones` → `"Developmental Growth"`

**4. Child name**  
- From profile: the parent app already gets the child’s profile (including name) from jubu_datastore / profile APIs using the same **child_id**.

---

## 5. Recommended UI structure (per child, on Profile Details)

**Placement:** Profile Details page, **above** the “Recent Conversations” section.

**Layout:**

- **Header for the section**  
  - One short **summary_sentence** for the child (e.g. “Lucy has shown curiosity about animals, recognizes feelings in stories, and joins imaginative play.”).  
  - No “today” or session-specific wording; this is about the child overall.

- **One expandable control (button / accordion)**  
  - All **categories (frameworks)** are grouped under **one** button (e.g. “See what Lucy is exploring” or “Discoveries & growth”).  
  - When the user **opens** this button, content **expands** to show the categories and their items.

- **Inside the expanded area**  
  - **Per framework/category:**  
    - Category title = **framework_display_name** (e.g. “Social Emotional Learning”, “Developmental Growth”).  
  - **Per item (under each category):**  
    - **parent_friendly_label** (e.g. “Recognizes feelings”, “Shows empathy”).  
    - **Marker** indicating the child’s status:  
      - **Mastered** when `status === "demonstrated"`.  
      - **Exposed to it** when `status === "emerging"`.  
      - **Not at all** when `status === "not_observed"`.

So: one button → expand → categories with items between them, each item with a single status marker (mastered / exposed / not at all).

- **Optional footer**  
  - “Suggested next activity” or “What to explore next” — placeholder if not implemented.

---

## 6. Reference files (in jubu_datastore)

| Purpose | File(s) |
|--------|---------|
| Example item shape, `parent_friendly_label`, framework ids | `capability_definitions/casel/age_5.yaml`, `capability_definitions/developmental/age_5.yaml` |
| State and observation DTOs | `dto/entities.py` — `ChildCapabilityState`, `CapabilityObservation` |
| Status and display fields | `models/capability_definitions.py` — scoring values (not_observed, emerging, demonstrated), `DisplayConfig`, `CapabilityItemDefinition` |
| How state is grouped by framework | `capability_datastore.py` — `get_child_capability_state(child_id)` |
| How to get definitions/labels | `loaders/capability_loader.py` — `get_item(item_id)`, `get_all_items_definitions()`, `load_default_registry()` |

---

## 7. What the parent app should and should not do

**Do:**

- **Do** use **jubu_datastore** as the **only** source for insights data: `CapabilityDatastore.get_child_capability_state(child_id)` and `CapabilityDefinitionRegistry.get_item(item_id)` (with a registry from `load_default_registry()` or your app’s config).
- **Do** use **child_id** (and child name from profile) to drive the Insights section.
- **Do** build the UI structure (frameworks, items, labels, status markers) in the parent app from the datastore responses.
- **Do** keep a small mapping for framework_id → framework_display_name in the parent app (or shared code).

**Do not:**

- **Do not** call or depend on **jubu_backend** for this feature. Parent app and jubu_backend do not communicate.
- **Do not** load or parse YAML capability definition files directly; use the **registry** from jubu_datastore.
- **Do not** implement evaluation or scoring logic; only read **state** and **definitions** from jubu_datastore.
- **Do not** invent framework display names or item labels; use `registry.get_item(item_id).parent_friendly_label` and the framework mapping above.

---

## 8. Pasteable instruction brief for the parent-app coder

**Task:** Add a “Child Discoveries / Insights” section on the **child’s Profile Details** page, **above** “Recent Conversations.” It is **per child** (not per conversation) and always visible.

**Data source:** **jubu_datastore only** (no jubu_backend). You have **child_id** (and **child_name** from profile).  
- Call **CapabilityDatastore.get_child_capability_state(child_id)** → state grouped by framework (each state has `item_id`, `current_status`).  
- Use **CapabilityDefinitionRegistry** (e.g. from **load_default_registry()**): for each `item_id`, call **registry.get_item(item_id)** to get **parent_friendly_label**.  
- Map framework_id to display name: `casel` → “Social Emotional Learning”, `developmental_milestones` → “Developmental Growth”.  
- Build a **summary_sentence** from item labels and statuses (or use a placeholder).

**UI:**  
- Place the section above Recent Conversations.  
- Show the one-sentence **summary_sentence** (child-level summary, not “today”).  
- **One expandable control (button):** e.g. “See what [child_name] is exploring” or “Discoveries & growth.” All categories live under this one button.  
- **When expanded:** show each **framework_display_name** as a category; under each category, list **items** with **parent_friendly_label** and a **marker**:  
  - **Mastered** when `current_status === "demonstrated"`.  
  - **Exposed to it** when `current_status === "emerging"`.  
  - **Not at all** when `current_status === "not_observed"`.  
- Optional: “Suggested next activity” at the bottom (placeholder if null).

**Rules:**  
- Get all data from **jubu_datastore** (CapabilityDatastore + CapabilityDefinitionRegistry). Do **not** call jubu_backend.  
- Do not load YAML or implement evaluation; only read state and definitions from the datastore.  
- Tone: child’s journey so far, not “Assessment results.”

**Reference (read-only):** See `capability_definitions/casel/age_5.yaml` and `developmental/age_5.yaml` for item structure; see `dto/entities.py` and `models/capability_definitions.py` for state/status fields; see `capability_datastore.py` and `loaders/capability_loader.py` for the APIs to call.
