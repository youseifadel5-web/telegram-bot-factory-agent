PLUGIN_ID = "orion"
PLUGIN_NAME = "أوريون بلس"
PLUGIN_BUTTON = "🎞️ أوريون بلس"


def open_plugin(call, context):
    return "cinema:hub_orion"


def handle_callback(call, context):
    return bool(context["cinema"].handle_callbacks(call))


def handle_message(update, context):
    return False


def search(query, context):
    results = context["cinema"].unified_search_results(query)
    return {
        "movie": results.get("orion_movies", []),
        "series": results.get("orion_series", []),
    }
