PLUGIN_ID = "youseif"
PLUGIN_NAME = "Youseif Films"
PLUGIN_BUTTON = "🎬 Youseif Films"


def open_plugin(call, context):
    return "youseif"


def handle_callback(call, context):
    return False


def handle_message(update, context):
    return False


def search(query, context):
    # The main launcher supplies the already initialized Youseif store.
    return context["youseif_store"].search(query)
