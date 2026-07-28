from django.db import models

# adminpanel has no models of its own. Its pages read and act on data
# owned by other apps (accounts.User, providers models) -- it's a
# management surface, not a data owner.
