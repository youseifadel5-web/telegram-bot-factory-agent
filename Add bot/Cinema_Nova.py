PLUGIN_ID = "nova"
PLUGIN_NAME = "سينما نوفا"
PLUGIN_BUTTON = "🌟 سينما نوفا"


def open_plugin(call, context):
    return "cinema:hub_nova"


def handle_callback(call, context):
    return bool(context["cinema"].handle_callbacks(call))


def handle_message(update, context):
    return False


def search(query, context):
    results = context["cinema"].unified_search_results(query)
    return {
        "movie": results.get("nova_movies", []),
        "series": results.get("nova_series", []),
    }
