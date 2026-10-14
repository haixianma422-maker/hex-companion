"""Release Tcl image handles on their owning widget's UI thread."""
import weakref
from PIL import ImageTk


class WidgetPhotoImage(ImageTk.PhotoImage):
    def __init__(self,image,master):
        self.released=False
        super().__init__(image,master=master)
        registry=getattr(master,'_owned_tk_images',None)
        if registry is None:
            registry=weakref.WeakSet()
            master._owned_tk_images=registry
            owner=weakref.ref(master)
            original_destroy=master.destroy
            def release_all():
                for photo in list(registry):
                    photo.release()
                registry.clear()
            def destroy():
                # Composite controls may forward bindings to an inner widget.
                # Explicit destruction releases the actual image owner too.
                release_all()
                original_destroy()
            master.destroy=destroy
            def dispose(event):
                if event.widget is owner():
                    release_all()
            master.bind('<Destroy>',dispose,add='+')
        registry.add(self)

    def release(self):
        if not self.released:
            self.released=True
            super().__del__()

    def __del__(self):
        # Widget destruction releases pictures retained by Python reference
        # cycles. Later worker-thread GC then performs no Tcl calls.
        if not getattr(self,'released',False):
            self.release()
