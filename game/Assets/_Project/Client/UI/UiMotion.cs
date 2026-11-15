using UnityEngine.UIElements;

namespace Recoil.Client.UI
{
    /// <summary>
    /// Small bits of movement for the interface, driven by the transitions in HudStyles.uss.
    /// Everything here moves or scales; nothing fades, because text inside an element whose
    /// opacity is animating can be left undrawn until it is next redrawn (by a hover, say).
    /// Each movement also redraws what it moved once it has settled, to be sure.
    /// </summary>
    public static class UiMotion
    {
        /// <summary>Slides an element up into place: it starts with the "enter" class, which comes off a frame later.</summary>
        public static void Enter(VisualElement element, long delayMs = 0)
        {
            if (element == null) return;
            element.AddToClassList("enter");
            element.schedule.Execute(() => element.RemoveFromClassList("enter")).StartingIn(16 + delayMs);
            RedrawLater(element, 300 + delayMs);
        }

        /// <summary>Re-runs a punch-in on an element whose text just changed.</summary>
        public static void Pop(VisualElement element, string startClass)
        {
            if (element == null) return;
            element.AddToClassList(startClass);
            element.schedule.Execute(() => element.RemoveFromClassList(startClass)).StartingIn(16);
            RedrawLater(element, 300);
        }

        /// <summary>Asks for the element and everything in it to be drawn again.</summary>
        public static void Redraw(VisualElement element)
        {
            if (element == null) return;
            element.MarkDirtyRepaint();
            element.Query<VisualElement>().ForEach(child => child.MarkDirtyRepaint());
        }

        /// <summary>
        /// Redraws once the motion has settled, and twice more after that: text whose letters
        /// were still being added to the font's atlas when it was first drawn is drawn again
        /// once they are there, instead of waiting for the mouse to pass over it.
        /// </summary>
        static void RedrawLater(VisualElement element, long delayMs)
        {
            element.schedule.Execute(() => Redraw(element)).StartingIn(delayMs);
            element.schedule.Execute(() => Redraw(element)).StartingIn(delayMs + 400);
            element.schedule.Execute(() => Redraw(element)).StartingIn(delayMs + 1200);
        }
    }
}
