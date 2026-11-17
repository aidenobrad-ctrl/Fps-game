using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.UIElements;
using Recoil.Client.Audio;
using Recoil.Client.Online;
using Recoil.Client.UI;
using Recoil.Shared.Match;
using Recoil.Shared.Progression;
using Cursor = UnityEngine.Cursor;

namespace Recoil.Client.Duel
{
    /// <summary>One line of the scoreboard.</summary>
    public struct ScoreRow
    {
        public string Name;
        public int Team;
        public int Kills, Deaths, Score;
        public bool Local, Bot, Alive;
    }

    /// <summary>Whose good news a kill feed line is.</summary>
    public enum FeedTone
    {
        Neutral,
        Ours,
        Theirs,
    }

    /// <summary>
    /// Everything on screen that belongs to online play rather than to the weapon in your
    /// hands: the menu (find a match, host a private one, join by address), and during a
    /// match the scores, the clock, the zones, your health, the kill feed, the scoreboard and
    /// the big announcements.
    ///
    /// It sits on top of the ordinary HUD and only shows what it is told. The match's logic
    /// lives in <see cref="DuelBootstrap"/>.
    /// </summary>
    [DisallowMultipleComponent]
    public sealed class DuelUi : MonoBehaviour
    {
        const string NameKey = "pb.playerName", AddressKey = "pb.lastAddress", ModeKey = "pb.mode";
        const string MapKey = "pb.host.map", SizeKey = "pb.host.size", BotsKey = "pb.host.bots", LimitKey = "pb.host.limit5.";
        const float KillFeedSeconds = 6f;
        const int KillFeedLines = 5;

        public static readonly Color Accent = new Color32(38, 216, 255, 255);
        static readonly Color Text = new Color32(240, 244, 250, 255);
        static readonly Color Dim = new Color(0.94f, 0.96f, 0.98f, 0.62f);
        static readonly Color Good = new Color32(96, 232, 140, 255);
        public static readonly Color Bad = new Color32(255, 96, 84, 255);
        static readonly Color Panel = new Color(0.04f, 0.06f, 0.08f, 0.72f);

        /// <summary>The order modes are offered in.</summary>
        public static readonly GameModeKind[] Modes =
        {
            GameModeKind.Duel, GameModeKind.TeamDeathmatch, GameModeKind.FreeForAll, GameModeKind.Elimination,
            GameModeKind.Domination, GameModeKind.Hardpoint, GameModeKind.GunGame,
        };

        static readonly string[] BotChoices = { "No bots", "Easy bots", "Normal bots", "Hard bots" };

        VisualElement _menu, _match, _menuCard, _pages, _home, _backdrop, _extras, _challengeList, _lastMatchPanel, _modeGrid;
        Page _page;
        Label _homeStatus, _crumb, _season, _chipLevel, _chipName, _footerHint, _lastMatchLine, _lastMatchDetail, _modeTitle;
        Button _playButton, _backButton;
        readonly List<Button> _modeTiles = new List<Button>();
        static Texture2D _shade, _fallbackArt;
        bool _overlayOpenLastFrame;
        VisualElement _chatBox, _chatLines;
        TextField _chatField;
        Label _chatScope;
        bool _chatTeam;
        readonly List<Label> _chat = new List<Label>();
        readonly List<float> _chatAge = new List<float>();
        const int ChatLinesShown = 8;
        const float ChatSeconds = 12f;
        Label _medal, _medalLine, _deathTitle, _deathLine;
        VisualElement _death;
        float _medalTimer;
        TextField _nameField, _addressField;
        DropdownField _modeField, _mapField, _sizeField, _botsField, _limitField, _timeField, _healthField, _respawnField, _weaponsField;
        readonly List<float> _times = new List<float>();
        static readonly int[] HealthChoices = { 50, 100, 150, 200 };
        static readonly float[] RespawnChoices = { 0f, 2f, 4f, 6f };
        const string TimeKey = "pb.host.time", HealthKey = "pb.host.health", RespawnKey = "pb.host.respawn", WeaponsKey = "pb.host.weapons";
        Label _modeHint, _menuStatus, _rankedHint, _levelText, _xpText;
        Toggle _rankedToggle;
        VisualElement _profile, _xpFill;
        Button _progressButton;
        Button _findButton, _hostToggle, _startButton, _joinButton, _rangeButton, _customizeButton, _quitButton, _cancelButton;
        VisualElement _hostOptions;

        Label _scoreLeft, _scoreRight, _nameLeft, _nameRight, _round, _clock, _status;
        Label _bannerTitle, _bannerSub, _notice, _netStats, _healthText;
        VisualElement _healthFill, _zoneStrip, _scoreboard, _scoreboardBody;
        Label _scoreboardTitle;
        readonly List<Zone> _zoneBadges = new List<Zone>();
        readonly List<Label> _feed = new List<Label>();
        readonly List<float> _feedAge = new List<float>();
        VisualElement _feedBox;

        struct Zone
        {
            public VisualElement Box, Fill;
            public Label Letter;
        }

        /// <summary>Argument: the mode chosen in the menu.</summary>
        /// <summary>Arguments: the mode, and whether to play it ranked.</summary>
        public event Action<GameModeKind, bool> FindRequested;
        public event Action ProgressRequested;
        /// <summary>Argument: the private match's rules, as set in the menu.</summary>
        public event Action<MatchSettings> HostRequested;
        /// <summary>Argument: the address typed in.</summary>
        public event Action<string> JoinRequested;
        public event Action RangeRequested;
        public event Action CustomizeRequested;
        public event Action QuitRequested;
        /// <summary>Pressed while searching for a match, or connecting to one.</summary>
        public event Action CancelRequested;

        public string PlayerName => _nameField != null ? _nameField.value.Trim() : "";
        public GameModeKind SelectedMode => Modes[Mathf.Clamp(_modeField != null ? _modeField.index : 0, 0, Modes.Length - 1)];

        AccountPanel _account;
        SocialPanel _social;
        GameServices _services;
        bool _busy;

        /// <param name="services">The player's account and loadouts. The menu shows who is signed in and offers the sign-in forms.</param>
        public static DuelUi Create(GameServices services)
        {
            var go = new GameObject("Online UI");
            var document = go.AddComponent<UIDocument>();
            document.panelSettings = HudController.LoadPanel();
            document.sortingOrder = 10f;

            var ui = go.AddComponent<DuelUi>();
            ui._services = services;
            ui.Build(document.rootVisualElement);
            return ui;
        }

        /// <summary>One sentence on what a mode is, for the menu.</summary>
        public static string Describe(GameModeKind mode)
        {
            switch (mode)
            {
                case GameModeKind.Duel: return "One on one, no respawns. First to win five rounds.";
                case GameModeKind.TeamDeathmatch: return "Two teams, respawns on. First team to five kills.";
                case GameModeKind.FreeForAll: return "Everyone for themselves, respawns on. First to five kills.";
                case GameModeKind.Elimination: return "Two teams, no respawns within a round. First to win five rounds.";
                case GameModeKind.Domination: return "Take and hold three zones. Every zone held scores a point a second.";
                case GameModeKind.Hardpoint: return "One zone at a time, moving every minute. Hold it alone to score.";
                case GameModeKind.GunGame: return "Every kill moves you to the next weapon. A knife kill with the last one wins.";
                default: return "";
            }
        }

        // ------------------------------------------------------------------ construction

        void Build(VisualElement root)
        {
            if (root == null)
            {
                Debug.LogError("Recoil: the online UI could not be created (no UI root).");
                return;
            }

            // The look comes from the HUD's stylesheet. The layout that matters is also set
            // here in code, so a missing stylesheet costs polish, not a usable menu.
            var styles = Resources.Load<StyleSheet>("UI/HudStyles");
            if (styles != null) root.styleSheets.Add(styles);
            else Debug.LogWarning("Recoil: Resources/UI/HudStyles.uss did not load; the online menu will look plain.");
            root.AddToClassList("hud");
            root.pickingMode = PickingMode.Ignore;
            Fill(root);
            root.style.color = Text;
            root.style.fontSize = 16;

            BuildMatch(root);
            BuildMenu(root);
            UiSounds.Attach(root);
            ShowMatch(false);
            ShowMenu("");
        }

        void BuildMenu(VisualElement root)
        {
            // The whole screen: art behind everything, a bar across the top, the page in the
            // middle with friends and party to its right, and a footer.
            _menu = new VisualElement();
            _menu.AddToClassList("pause");
            _menu.AddToClassList("main-menu");
            Fill(_menu);
            _menu.style.flexDirection = FlexDirection.Column;
            _menu.style.alignItems = Align.Stretch;
            _menu.style.justifyContent = Justify.FlexStart;
            _menu.style.backgroundColor = new Color(0.027f, 0.035f, 0.055f, 1f);
            _menu.style.overflow = Overflow.Hidden;
            root.Add(_menu);

            _backdrop = new VisualElement { pickingMode = PickingMode.Ignore };
            _backdrop.AddToClassList("menu-backdrop");
            Fill(_backdrop);
            Texture2D art = Resources.Load<Texture2D>("UI/MenuBackdrop");
            _backdrop.style.backgroundImage = new StyleBackground(art != null ? art : FallbackBackdrop());
            _menu.Add(_backdrop);
            var shade = new VisualElement { pickingMode = PickingMode.Ignore };
            Fill(shade);
            shade.style.backgroundImage = new StyleBackground(MenuShade());
            _menu.Add(shade);
            // A slow drift, so the art feels alive rather than pasted on.
            _backdrop.schedule.Execute(DriftBackdrop).Every(33);

            BuildTopBar(_menu);

            var body = new VisualElement();
            body.style.flexGrow = 1;
            body.style.flexDirection = FlexDirection.Row;
            body.style.alignItems = Align.Stretch;
            body.style.minHeight = 0;
            _menu.Add(body);

            // One page at a time: home, play, or an account form.
            _pages = new VisualElement();
            _pages.style.flexGrow = 1;
            _pages.style.flexShrink = 1;
            _pages.style.flexDirection = FlexDirection.Row;
            _pages.style.alignItems = Align.Center;
            _pages.style.justifyContent = Justify.Center;
            body.Add(_pages);

            VisualElement accountHost = BuildHome(_pages);
            BuildPlayPage(_pages);

            if (_services != null && GameServices.AccountsEnabled)
            {
                _account = new AccountPanel(_services, _home, accountHost, _pages);
                // Signed in, a player goes by their account's name, so there is nothing to type.
                _account.Changed += () =>
                {
                    if (_nameField != null) _nameField.style.display = _services.Account.SignedIn ? DisplayStyle.None : DisplayStyle.Flex;
                    RefreshTopBar();
                };
            }
            _account?.Refresh();

            // Friends and party, down the right-hand side.
            if (_services != null && _services.Social != null)
            {
                var side = new VisualElement();
                side.style.justifyContent = Justify.Center;
                side.style.paddingRight = 40;
                side.style.paddingLeft = 8;
                body.Add(side);
                _social = new SocialPanel(side, _services.Social, _services.Account);
                _social.Root.style.maxHeight = Length.Percent(96);
                _services.Social.Changed += OnSocialChanged;
            }

            BuildFooter(_menu);

            ProgressionCache.Changed += RefreshHomeExtras;
            if (_services != null) _services.Account.Changed += RefreshHomeExtras;
            _menu.RegisterCallback<GeometryChangedEvent>(_ => FitToWidth());

            OnModeChanged();
            RefreshHomeExtras();
            ShowPage(Page.Home);
        }

        // ------------------------------------------------------------------ top bar and footer

        void BuildTopBar(VisualElement menu)
        {
            var bar = new VisualElement();
            bar.AddToClassList("menu-topbar");
            bar.style.flexDirection = FlexDirection.Row;
            bar.style.alignItems = Align.Center;
            bar.style.height = 72;
            bar.style.paddingLeft = 48;
            bar.style.paddingRight = 40;
            bar.style.flexShrink = 0;
            menu.Add(bar);

            _crumb = Text_("RECOIL", 18, Text, bold: true, spacing: 6);
            bar.Add(_crumb);
            _season = Text_("", 13, Dim, bold: true, spacing: 2);
            _season.style.marginLeft = 22;
            _season.style.paddingLeft = 22;
            _season.style.borderLeftWidth = 1;
            _season.style.borderLeftColor = new Color(1f, 1f, 1f, 0.18f);
            bar.Add(_season);

            var gap = new VisualElement { pickingMode = PickingMode.Ignore };
            gap.style.flexGrow = 1;
            bar.Add(gap);

            // Who is playing: a level badge and a name.
            var chip = new VisualElement();
            chip.AddToClassList("menu-chip");
            chip.style.flexDirection = FlexDirection.Row;
            chip.style.alignItems = Align.Center;
            chip.style.paddingLeft = 6;
            chip.style.paddingRight = 16;
            chip.style.height = 44;
            chip.style.backgroundColor = new Color(0.04f, 0.06f, 0.09f, 0.75f);
            chip.style.borderTopWidth = chip.style.borderBottomWidth = chip.style.borderLeftWidth = chip.style.borderRightWidth = 1;
            chip.style.borderTopColor = chip.style.borderBottomColor = chip.style.borderLeftColor = chip.style.borderRightColor = new Color(1f, 1f, 1f, 0.1f);
            Round(chip, 22);
            bar.Add(chip);
            _chipLevel = Text_("", 14, new Color32(6, 16, 22, 255), bold: true);
            _chipLevel.style.unityTextAlign = TextAnchor.MiddleCenter;
            _chipLevel.style.minWidth = 34;
            _chipLevel.style.height = 34;
            _chipLevel.style.paddingLeft = _chipLevel.style.paddingRight = 6;
            _chipLevel.style.backgroundColor = Accent;
            Round(_chipLevel, 17);
            chip.Add(_chipLevel);
            _chipName = Text_("", 16, Text, bold: true);
            _chipName.style.marginLeft = 12;
            chip.Add(_chipName);
            RefreshTopBar();
        }

        void BuildFooter(VisualElement menu)
        {
            var footer = new VisualElement();
            footer.AddToClassList("menu-footer");
            footer.style.flexDirection = FlexDirection.Row;
            footer.style.alignItems = Align.Center;
            footer.style.height = 44;
            footer.style.paddingLeft = 48;
            footer.style.paddingRight = 40;
            footer.style.flexShrink = 0;
            footer.style.backgroundColor = new Color(0f, 0f, 0f, 0.4f);
            footer.style.borderTopWidth = 1;
            footer.style.borderTopColor = new Color(1f, 1f, 1f, 0.07f);
            menu.Add(footer);

            _footerHint = Text_("", 13, Dim, bold: true, spacing: 2);
            footer.Add(_footerHint);
            var gap = new VisualElement { pickingMode = PickingMode.Ignore };
            gap.style.flexGrow = 1;
            footer.Add(gap);
            footer.Add(Text_("RECOIL  ·  v" + Application.version, 12, new Color(1f, 1f, 1f, 0.35f), spacing: 2));
        }

        void RefreshTopBar()
        {
            if (_chipName == null) return;
            bool signedIn = _services != null && _services.Account.SignedIn;
            ProgressionData progression = ProgressionCache.Current;
            string name = signedIn && _services.Account.Account != null ? _services.Account.Account.username : PlayerName;
            _chipName.text = string.IsNullOrEmpty(name) ? "Player" : name;
            _chipLevel.text = signedIn && progression != null ? progression.level.level.ToString() : "–";

            SeasonData season = signedIn && progression != null ? progression.season : null;
            long now = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            if (season != null && season.endsAt > now)
            {
                long days = (season.endsAt - now + 86399) / 86400;
                _season.text = "SEASON " + season.number + "   ·   " + days + (days == 1 ? " DAY LEFT" : " DAYS LEFT");
            }
            else
            {
                _season.text = "ARENA COMBAT";
            }
        }

        float _drift;

        void DriftBackdrop()
        {
            if (_backdrop == null || _menu.resolvedStyle.display == DisplayStyle.None) return;
            _drift += 0.033f;
            float scale = 1.06f + 0.025f * Mathf.Sin(_drift * 0.07f);
            _backdrop.style.scale = new Scale(new Vector3(scale, scale, 1f));
            _backdrop.style.translate = new Translate(Mathf.Sin(_drift * 0.045f) * 18f, Mathf.Cos(_drift * 0.06f) * 8f);
        }

        /// <summary>Narrow screens drop the extras first, so the buttons and the social panel always fit.</summary>
        void FitToWidth()
        {
            float width = _menu.resolvedStyle.width;
            if (float.IsNaN(width) || _extras == null) return;
            _extras.style.display = width >= 1750f ? DisplayStyle.Flex : DisplayStyle.None;
            if (_social != null) _social.Root.parent.style.display = width >= 1250f ? DisplayStyle.Flex : DisplayStyle.None;
        }

        // ------------------------------------------------------------------ home

        /// <summary>
        /// The home screen: the game's name, who is playing, and the big buttons, with the
        /// player's challenges beside them. Returns the place for the account summary.
        /// </summary>
        VisualElement BuildHome(VisualElement pages)
        {
            _home = new VisualElement();
            _home.AddToClassList("home");
            _home.style.flexGrow = 1;
            _home.style.alignSelf = Align.Stretch;
            _home.style.flexDirection = FlexDirection.Row;
            _home.style.alignItems = Align.Center;
            _home.style.paddingLeft = Length.Percent(6);
            _home.style.paddingRight = 24;
            pages.Add(_home);

            var left = new VisualElement();
            left.style.width = 480;
            left.style.flexShrink = 0;
            _home.Add(left);

            var brand = new VisualElement { pickingMode = PickingMode.Ignore };
            brand.style.marginBottom = 26;
            left.Add(brand);
            brand.Add(Text_("RECOIL", 112, Text, bold: true, spacing: 22, className: "home-title"));
            var bar = new VisualElement { pickingMode = PickingMode.Ignore };
            bar.AddToClassList("home-bar");
            bar.style.width = 160;
            bar.style.height = 5;
            bar.style.marginTop = -8;
            bar.style.backgroundColor = Accent;
            brand.Add(bar);
            Label tagline = Text_("FAST  ·  FAIR  ·  RELENTLESS", 14, Accent, bold: true, spacing: 6);
            tagline.style.marginTop = 14;
            brand.Add(tagline);

            var accountHost = new VisualElement();
            left.Add(accountHost);
            BuildProfile(left);

            _playButton = HomeButton("PLAY", "Quick match, ranked or a private game", true, () => ShowPage(Page.Play));
            _customizeButton = HomeButton("CUSTOMIZE", "Loadouts, attachments and your look", false, () => CustomizeRequested?.Invoke());
            _rangeButton = HomeButton("FIRING RANGE", "Warm up on targets at every distance", false, () => RangeRequested?.Invoke());
            Button settings = HomeButton("SETTINGS", "Controls, video, audio and gameplay", false, () => SettingsScreen.Open());
            _quitButton = HomeButton("QUIT", "Back to the desktop", false, () => QuitRequested?.Invoke());
            foreach (Button button in new[] { _playButton, _customizeButton, _rangeButton, settings, _quitButton })
                left.Add(button);
            _quitButton.style.marginTop = 12;

            _homeStatus = Text_("", 14, Bad);
            _homeStatus.style.whiteSpace = WhiteSpace.Normal;
            _homeStatus.style.marginTop = 10;
            _homeStatus.style.minHeight = 20;
            left.Add(_homeStatus);

            var gap = new VisualElement { pickingMode = PickingMode.Ignore };
            gap.style.flexGrow = 1;
            _home.Add(gap);

            BuildExtras(_home);
            return accountHost;
        }

        /// <summary>Beside the buttons: this player's challenges, and how their last match went.</summary>
        void BuildExtras(VisualElement home)
        {
            _extras = new VisualElement();
            _extras.style.width = 400;
            _extras.style.flexShrink = 0;
            _extras.style.alignSelf = Align.FlexEnd;
            _extras.style.marginBottom = 40;
            home.Add(_extras);

            VisualElement challenges = MenuPanel(_extras, "CHALLENGES");
            _challengeList = new VisualElement();
            challenges.Add(_challengeList);

            _lastMatchPanel = MenuPanel(_extras, "LAST MATCH");
            _lastMatchPanel.style.marginTop = 14;
            _lastMatchLine = Text_("", 15, Text, bold: true);
            _lastMatchLine.style.whiteSpace = WhiteSpace.Normal;
            _lastMatchPanel.Add(_lastMatchLine);
            _lastMatchDetail = Text_("", 13, Dim);
            _lastMatchDetail.style.whiteSpace = WhiteSpace.Normal;
            _lastMatchDetail.style.marginTop = 4;
            _lastMatchPanel.Add(_lastMatchDetail);
        }

        /// <summary>A glassy panel with a small heading, for the menu's side content.</summary>
        static VisualElement MenuPanel(VisualElement parent, string heading)
        {
            var panel = new VisualElement();
            panel.AddToClassList("menu-panel");
            panel.style.paddingLeft = panel.style.paddingRight = 20;
            panel.style.paddingTop = 16;
            panel.style.paddingBottom = 18;
            panel.style.backgroundColor = new Color(0.035f, 0.05f, 0.075f, 0.82f);
            panel.style.borderTopWidth = 2;
            panel.style.borderTopColor = Accent;
            Round(panel, 6);
            parent.Add(panel);
            Label title = Text_(heading, 13, Accent, bold: true, spacing: 4);
            title.style.marginBottom = 10;
            panel.Add(title);
            return panel;
        }

        void RefreshHomeExtras()
        {
            RefreshTopBar();
            if (_challengeList == null) return;
            _challengeList.Clear();
            bool signedIn = _services != null && _services.Account.SignedIn;
            ProgressionData progression = ProgressionCache.Current;

            if (!signedIn || progression == null)
            {
                Label hint = Text_(signedIn ? "Fetching your challenges..." : "Sign in to take on daily and weekly challenges, earn XP and climb the ranks.", 14, Dim);
                hint.style.whiteSpace = WhiteSpace.Normal;
                _challengeList.Add(hint);
                _lastMatchPanel.style.display = DisplayStyle.None;
                return;
            }

            int shown = 0;
            foreach (ChallengeData challenge in progression.challenges)
            {
                if (shown >= 4) break;
                shown++;
                var row = new VisualElement { pickingMode = PickingMode.Ignore };
                row.style.marginBottom = 10;
                _challengeList.Add(row);
                var line = Row(row);
                line.style.justifyContent = Justify.SpaceBetween;
                Label text = Text_((challenge.weekly ? "WEEKLY  " : "") + challenge.text, 13, challenge.completed ? Good : Text);
                text.style.whiteSpace = WhiteSpace.Normal;
                text.style.flexShrink = 1;
                line.Add(text);
                Label count = Text_(challenge.completed ? "DONE" : Mathf.Min(challenge.progress, challenge.goal) + "/" + challenge.goal, 12,
                    challenge.completed ? Good : Dim, bold: true);
                count.style.marginLeft = 10;
                line.Add(count);
                var track = new VisualElement { pickingMode = PickingMode.Ignore };
                track.style.height = 4;
                track.style.marginTop = 5;
                track.style.backgroundColor = new Color(1f, 1f, 1f, 0.08f);
                Round(track, 2);
                row.Add(track);
                var fill = new VisualElement { pickingMode = PickingMode.Ignore };
                fill.style.height = Length.Percent(100);
                fill.style.width = Length.Percent(Mathf.Clamp01(challenge.goal > 0 ? challenge.progress / (float)challenge.goal : 1f) * 100f);
                fill.style.backgroundColor = challenge.completed ? Good : Accent;
                Round(fill, 2);
                track.Add(fill);
            }
            if (shown == 0) _challengeList.Add(Text_("All done for now. New ones arrive soon.", 14, Dim));

            LastMatchData last = progression.lastMatch;
            bool hasLast = last != null && !string.IsNullOrEmpty(last.matchId);
            _lastMatchPanel.style.display = hasLast ? DisplayStyle.Flex : DisplayStyle.None;
            if (hasLast)
            {
                _lastMatchLine.text = DescribeLastMatch(last);
                _lastMatchDetail.text = LastMatchDetail(last);
            }
        }

        static string DescribeLastMatch(LastMatchData last)
        {
            Playlist playlist = Playlists.Find(last.playlist);
            string title = playlist != null ? playlist.Title : last.playlist;
            string outcome = last.outcome == 2 ? "Won" : last.outcome == 0 ? "Lost" : "Drew";
            return outcome + " a " + (last.ranked ? "ranked " : "") + title + " match";
        }

        static string LastMatchDetail(LastMatchData last)
        {
            string line = "+" + last.xpGained + " XP";
            if (last.levelAfter > last.levelBefore) line += "   ·   level " + last.levelAfter + "!";
            if (last.ranked && last.ratingAfter != last.ratingBefore)
                line += "   ·   rating " + (last.ratingAfter > last.ratingBefore ? "+" : "") + (last.ratingAfter - last.ratingBefore);
            return line;
        }

        static Button HomeButton(string title, string caption, bool primary, Action onClick)
        {
            var button = new Button(onClick) { text = "" };
            button.AddToClassList("home-button");
            if (primary) button.AddToClassList("primary");
            // The look is in the stylesheet; the size is here too, so a missing sheet still leaves big buttons.
            button.style.height = primary ? 76 : 58;
            button.style.marginLeft = 0;
            button.style.marginRight = 0;
            button.style.marginBottom = 8;
            button.style.flexDirection = FlexDirection.Column;
            button.style.justifyContent = Justify.Center;
            button.style.alignItems = Align.FlexStart;

            Color ink = primary ? (Color)new Color32(6, 16, 22, 255) : Text;
            Label name = Text_(title, primary ? 30 : 20, ink, bold: true, spacing: primary ? 8 : 4);
            name.AddToClassList("home-button__title");
            button.Add(name);
            Label sub = Text_(caption, 12, new Color(ink.r, ink.g, ink.b, 0.62f));
            sub.AddToClassList("home-button__caption");
            sub.style.marginTop = 1;
            button.Add(sub);
            return button;
        }

        // ------------------------------------------------------------------ play

        /// <summary>
        /// The play page: every mode as a tile across the screen, and down the right, finding
        /// a match, hosting a private one, or joining one by address.
        /// </summary>
        void BuildPlayPage(VisualElement pages)
        {
            var page = new VisualElement();
            page.AddToClassList("play-page");
            page.style.flexGrow = 1;
            page.style.alignSelf = Align.Stretch;
            page.style.flexDirection = FlexDirection.Row;
            page.style.paddingLeft = 48;
            page.style.paddingRight = 16;
            page.style.paddingTop = 8;
            page.style.paddingBottom = 16;
            pages.Add(page);
            _menuCard = page;

            // Left: the header and the mode tiles.
            var left = new VisualElement();
            left.style.flexGrow = 1;
            left.style.flexShrink = 1;
            left.style.minWidth = 0;
            page.Add(left);

            var header = Row(left);
            header.pickingMode = PickingMode.Position;
            header.style.alignItems = Align.Center;
            header.style.marginBottom = 20;
            _backButton = MenuButton("◂  BACK", false, () => ShowPage(Page.Home));
            _backButton.AddToClassList("back-button");
            _backButton.style.marginLeft = 0;
            _backButton.style.minWidth = 110;
            _backButton.style.height = 40;
            header.Add(_backButton);
            Label title = Text_("PLAY", 48, Text, bold: true, spacing: 10);
            title.style.marginLeft = 24;
            header.Add(title);

            left.Add(Text_("CHOOSE A MODE", 13, Accent, bold: true, spacing: 4));
            _modeGrid = new VisualElement();
            _modeGrid.style.flexDirection = FlexDirection.Row;
            _modeGrid.style.flexWrap = Wrap.Wrap;
            _modeGrid.style.marginTop = 12;
            left.Add(_modeGrid);
            _modeTiles.Clear();
            for (int i = 0; i < Modes.Length; i++)
            {
                int index = i;
                _modeTiles.Add(ModeTile(_modeGrid, Modes[i], () =>
                {
                    if (_modeField.index != index) _modeField.index = index;
                }));
            }

            // Right: how to get into a match, in a column that scrolls if the private match's options run long.
            var scroll = new ScrollView(ScrollViewMode.Vertical);
            scroll.style.width = 470;
            scroll.style.flexShrink = 0;
            scroll.style.marginLeft = 28;
            page.Add(scroll);
            VisualElement column = scroll.contentContainer;

            VisualElement match = MenuPanel(column, "MATCHMAKING");
            _modeTitle = Text_("", 30, Text, bold: true, spacing: 3);
            match.Add(_modeTitle);
            _modeHint = Text_("", 13, Dim);
            _modeHint.style.whiteSpace = WhiteSpace.Normal;
            _modeHint.style.marginTop = 2;
            _modeHint.style.marginBottom = 12;
            match.Add(_modeHint);

            _nameField = new TextField("Name") { value = PlayerPrefs.GetString(NameKey, "Player"), maxLength = 24 };
            _nameField.AddToClassList("loadout-name");
            _nameField.style.fontSize = 16;
            _nameField.style.marginLeft = 0;
            _nameField.RegisterValueChangedCallback(_ => RefreshTopBar());
            match.Add(_nameField);

            // The mode's dropdown stays the one record of which mode is chosen; the tiles set it.
            var modeNames = new List<string>();
            foreach (GameModeKind mode in Modes) modeNames.Add(MatchSettings.Title(mode));
            _modeField = Dropdown(match, "Mode", modeNames, Mathf.Clamp(PlayerPrefs.GetInt(ModeKey, 0), 0, Modes.Length - 1));
            _modeField.style.display = DisplayStyle.None;
            _modeField.RegisterValueChangedCallback(_ => OnModeChanged());

            // Ranked, for the modes that have it.
            var rankedRow = new VisualElement();
            rankedRow.style.flexDirection = FlexDirection.Row;
            rankedRow.style.alignItems = Align.Center;
            rankedRow.style.marginBottom = 10;
            _rankedToggle = new Toggle("Ranked") { value = false };
            _rankedToggle.style.fontSize = 15;
            _rankedToggle.RegisterValueChangedCallback(_ => RefreshRanked());
            rankedRow.Add(_rankedToggle);
            _rankedHint = Text_("", 12, Dim);
            _rankedHint.style.marginLeft = 12;
            _rankedHint.style.whiteSpace = WhiteSpace.Normal;
            _rankedHint.style.flexShrink = 1;
            rankedRow.Add(_rankedHint);
            match.Add(rankedRow);

            _findButton = MenuButton("FIND MATCH", true, () =>
            {
                Remember();
                FindRequested?.Invoke(SelectedMode, RankedChosen);
            });
            _findButton.AddToClassList("find-button");
            _findButton.style.height = 58;
            _findButton.style.fontSize = 22;
            match.Add(_findButton);

            _menuStatus = Text_("", 14, Bad);
            _menuStatus.style.whiteSpace = WhiteSpace.Normal;
            _menuStatus.style.marginTop = 10;
            _menuStatus.style.minHeight = 20;
            match.Add(_menuStatus);
            _cancelButton = MenuButton("CANCEL", false, () => CancelRequested?.Invoke());
            _cancelButton.style.marginLeft = 0;
            _cancelButton.style.marginTop = 4;
            match.Add(_cancelButton);

            // A private match: the host picks every rule.
            VisualElement host = MenuPanel(column, "PRIVATE MATCH");
            host.style.marginTop = 14;
            _hostToggle = MenuButton("Host a private match  ▾", false, () => SetHostOptions(_hostOptions.style.display == DisplayStyle.None));
            _hostToggle.style.marginLeft = 0;
            host.Add(_hostToggle);

            _hostOptions = new VisualElement();
            _hostOptions.style.marginTop = 6;
            host.Add(_hostOptions);
            _mapField = Dropdown(_hostOptions, "Map", new List<string>(), 0);
            _sizeField = Dropdown(_hostOptions, "Players", new List<string>(), 0);
            _limitField = Dropdown(_hostOptions, "Win at", new List<string>(), 0);
            _botsField = Dropdown(_hostOptions, "Empty places", new List<string>(BotChoices), Mathf.Clamp(PlayerPrefs.GetInt(BotsKey, 2), 0, 3));
            _timeField = Dropdown(_hostOptions, "Time limit", new List<string>(), 0);
            var healthNames = new List<string>();
            foreach (int health in HealthChoices) healthNames.Add(health + " health");
            _healthField = Dropdown(_hostOptions, "Health", healthNames, Mathf.Max(0, Array.IndexOf(HealthChoices, PlayerPrefs.GetInt(HealthKey, 100))));
            var respawnNames = new List<string>();
            foreach (float delay in RespawnChoices) respawnNames.Add(delay <= 0f ? "Straight away" : delay + " seconds");
            _respawnField = Dropdown(_hostOptions, "Respawn after", respawnNames, 0);
            var weaponNames = new List<string>();
            foreach (WeaponRule rule in WeaponRules.All) weaponNames.Add(WeaponRules.Title(rule));
            _weaponsField = Dropdown(_hostOptions, "Weapons", weaponNames, Mathf.Clamp(PlayerPrefs.GetInt(WeaponsKey, 0), 0, WeaponRules.All.Length - 1));
            Label hostHint = Text_("Bots fill any place nobody has taken, and step aside when someone joins. Others join with your address.", 12, Dim);
            hostHint.style.whiteSpace = WhiteSpace.Normal;
            _hostOptions.Add(hostHint);
            _startButton = MenuButton("START PRIVATE MATCH", true, () =>
            {
                Remember();
                HostRequested?.Invoke(BuildSettings());
            });
            _startButton.style.marginTop = 8;
            _hostOptions.Add(_startButton);
            SetHostOptions(false);

            // Straight to a server someone told you about.
            VisualElement join = MenuPanel(column, "DIRECT CONNECT");
            join.style.marginTop = 14;
            var joinRow = new VisualElement();
            joinRow.style.flexDirection = FlexDirection.Row;
            joinRow.style.alignItems = Align.Center;
            _addressField = new TextField { value = PlayerPrefs.GetString(AddressKey, "127.0.0.1"), maxLength = 64 };
            _addressField.AddToClassList("loadout-name");
            _addressField.style.fontSize = 16;
            _addressField.style.flexGrow = 1;
            _addressField.style.marginLeft = 0;
            joinRow.Add(_addressField);
            _joinButton = MenuButton("JOIN", false, RequestJoin);
            _joinButton.style.marginLeft = 10;
            _joinButton.style.minWidth = 100;
            joinRow.Add(_joinButton);
            join.Add(joinRow);
            // Enter in the address box joins. Which of these two events carries the key depends on the Unity version.
            _addressField.RegisterCallback<KeyDownEvent>(e =>
            {
                if (e.keyCode == KeyCode.Return || e.keyCode == KeyCode.KeypadEnter) RequestJoin();
            }, TrickleDown.TrickleDown);
            _addressField.RegisterCallback<NavigationSubmitEvent>(e => RequestJoin(), TrickleDown.TrickleDown);
        }

        /// <summary>One mode, as a tile: its name, how many play, and what it is about.</summary>
        static Button ModeTile(VisualElement grid, GameModeKind mode, Action onClick)
        {
            var tile = new Button(onClick) { text = "" };
            tile.AddToClassList("mode-tile");
            tile.style.width = 250;
            tile.style.height = 168;
            tile.style.marginLeft = 0;
            tile.style.marginRight = 14;
            tile.style.marginBottom = 14;
            tile.style.paddingLeft = tile.style.paddingRight = 18;
            tile.style.paddingTop = 16;
            tile.style.paddingBottom = 14;
            tile.style.flexDirection = FlexDirection.Column;
            tile.style.alignItems = Align.FlexStart;
            tile.style.justifyContent = Justify.FlexStart;
            grid.Add(tile);

            MatchSettings rules = MatchSettings.For(mode);
            string players = mode == GameModeKind.Duel ? "1 v 1"
                : rules.TeamBased ? rules.teamSize + " v " + rules.teamSize
                : "UP TO " + rules.Capacity + " PLAYERS";
            Label size = Text_(players, 12, Accent, bold: true, spacing: 3);
            size.AddToClassList("mode-tile__size");
            tile.Add(size);
            Label name = Text_(MatchSettings.Title(mode).ToUpperInvariant(), 21, Text, bold: true, spacing: 2);
            name.AddToClassList("mode-tile__name");
            name.style.marginTop = 6;
            name.style.whiteSpace = WhiteSpace.Normal;
            tile.Add(name);
            Label about = Text_(Describe(mode), 12, Dim);
            about.style.whiteSpace = WhiteSpace.Normal;
            about.style.marginTop = 8;
            tile.Add(about);
            return tile;
        }

        /// <summary>Lights the tile of the chosen mode.</summary>
        void RefreshModeTiles()
        {
            int chosen = _modeField != null ? _modeField.index : 0;
            for (int i = 0; i < _modeTiles.Count; i++) _modeTiles[i].EnableInClassList("mode-tile--chosen", i == chosen);
            if (_modeTitle != null) _modeTitle.text = MatchSettings.Title(SelectedMode).ToUpperInvariant();
        }

        // ------------------------------------------------------------------ the backdrop

        /// <summary>A left-to-right shade over the art, made once: dark behind the buttons, clearing towards the right.</summary>
        static Texture2D MenuShade()
        {
            if (_shade != null) return _shade;
            const int width = 128;
            _shade = new Texture2D(width, 1, TextureFormat.RGBA32, false)
            {
                name = "Menu Shade",
                wrapMode = TextureWrapMode.Clamp,
                filterMode = FilterMode.Bilinear,
                hideFlags = HideFlags.DontSave,
            };
            var pixels = new Color32[width];
            for (int x = 0; x < width; x++)
            {
                float t = x / (width - 1f);
                float alpha = Mathf.Lerp(0.9f, 0.15f, Mathf.SmoothStep(0f, 1f, Mathf.InverseLerp(0.18f, 0.7f, t)));
                pixels[x] = new Color(0.012f, 0.018f, 0.03f, alpha);
            }
            _shade.SetPixels32(pixels);
            _shade.Apply(false, true);
            return _shade;
        }

        /// <summary>If the art is missing: a dark field with a cool glow off to the right, drawn in code.</summary>
        static Texture2D FallbackBackdrop()
        {
            if (_fallbackArt != null) return _fallbackArt;
            const int w = 192, h = 108;
            _fallbackArt = new Texture2D(w, h, TextureFormat.RGBA32, false)
            {
                name = "Menu Backdrop (fallback)",
                wrapMode = TextureWrapMode.Clamp,
                filterMode = FilterMode.Bilinear,
                hideFlags = HideFlags.DontSave,
            };
            var pixels = new Color32[w * h];
            Color deep = new Color(0.02f, 0.03f, 0.05f), glow = new Color(0.05f, 0.32f, 0.42f), warm = new Color(0.35f, 0.14f, 0.05f);
            for (int y = 0; y < h; y++)
            {
                for (int x = 0; x < w; x++)
                {
                    float u = x / (float)w, v = y / (float)h;
                    float cool = Mathf.Exp(-((u - 0.72f) * (u - 0.72f) * 6f + (v - 0.55f) * (v - 0.55f) * 9f));
                    float hot = Mathf.Exp(-((u - 0.95f) * (u - 0.95f) * 14f + (v - 0.15f) * (v - 0.15f) * 20f));
                    Color c = deep + glow * cool * 0.9f + warm * hot * 0.6f;
                    // Faint lines across the floor, for depth.
                    if (v < 0.35f && Mathf.Repeat(u * 24f + v * 40f, 1f) < 0.04f) c += new Color(0.03f, 0.05f, 0.06f) * (0.35f - v) * 3f;
                    pixels[y * w + x] = c;
                }
            }
            _fallbackArt.SetPixels32(pixels);
            _fallbackArt.Apply(false, true);
            return _fallbackArt;
        }

        enum Page { Home, Play }

        /// <summary>Switches the menu between the home screen and the play page.</summary>
        void ShowPage(Page page)
        {
            if (_home == null || _menuCard == null) return;
            if (_account != null) _account.CloseForms();
            _page = page;
            _home.style.display = page == Page.Home ? DisplayStyle.Flex : DisplayStyle.None;
            _menuCard.style.display = page == Page.Play ? DisplayStyle.Flex : DisplayStyle.None;
            UiMotion.Enter(page == Page.Home ? _home : _menuCard);
            if (_crumb != null) _crumb.text = page == Page.Home ? "RECOIL" : "RECOIL  /  PLAY";
            if (_footerHint != null) _footerHint.text = page == Page.Home ? "" : "ESC   BACK";
            if (page == Page.Play)
            {
                RefreshRanked();
                RefreshModeTiles();
            }
            else
            {
                RefreshHomeExtras();
            }
        }

        static DropdownField Dropdown(VisualElement parent, string label, List<string> choices, int index)
        {
            var field = new DropdownField(label, choices, choices.Count > 0 ? Mathf.Clamp(index, 0, choices.Count - 1) : -1);
            field.style.fontSize = 15;
            parent.Add(field);
            return field;
        }

        void SetHostOptions(bool open)
        {
            _hostOptions.style.display = open ? DisplayStyle.Flex : DisplayStyle.None;
            _hostToggle.text = open ? "Host a private match  ▴" : "Host a private match  ▾";
        }

        // ------------------------------------------------------------------ the private match's rules

        GameModeKind _optionsFor = (GameModeKind)255;
        readonly List<string> _mapIds = new List<string>();
        readonly List<int> _sizes = new List<int>();
        readonly List<int> _limits = new List<int>();

        /// <summary>Refills the host options to suit the chosen mode.</summary>
        void OnModeChanged()
        {
            GameModeKind mode = SelectedMode;
            _modeHint.text = Describe(mode);
            RefreshModeTiles();
            RefreshRanked();
            if (mode == _optionsFor) return;
            _optionsFor = mode;
            MatchSettings defaults = MatchSettings.For(mode);

            _mapIds.Clear();
            var mapNames = new List<string>();
            foreach (string id in ArenaLayout.Ids)
            {
                var probe = defaults.Clone();
                probe.arenaId = id;
                probe.teamSize = 1;
                probe.maxPlayers = 2;
                if (!ArenaLayout.Find(id).Supports(probe)) continue;
                _mapIds.Add(id);
                mapNames.Add(ArenaLayout.Title(id));
            }
            SetChoices(_mapField, mapNames, Mathf.Max(0, _mapIds.IndexOf(PlayerPrefs.GetString(MapKey + mode, defaults.arenaId))));

            _sizes.Clear();
            var sizeNames = new List<string>();
            if (mode == GameModeKind.Duel)
            {
                _sizes.Add(1);
                sizeNames.Add("1 v 1");
            }
            else if (defaults.TeamBased)
            {
                for (int n = 1; n <= 5; n++)
                {
                    _sizes.Add(n);
                    sizeNames.Add(n + " v " + n);
                }
            }
            else
            {
                for (int n = 2; n <= 12; n += 2)
                {
                    _sizes.Add(n);
                    sizeNames.Add("Up to " + n);
                }
            }
            int size = PlayerPrefs.GetInt(SizeKey + mode, defaults.TeamBased ? defaults.teamSize : defaults.maxPlayers);
            SetChoices(_sizeField, sizeNames, Mathf.Max(0, _sizes.IndexOf(size)));
            _sizeField.label = defaults.TeamBased ? "Teams" : "Players";

            _limits.Clear();
            var limitNames = new List<string>();
            if (mode == GameModeKind.GunGame)
            {
                _limits.Add(GunGameLadder.Length);
                limitNames.Add("The last weapon (" + GunGameLadder.Length + " kills)");
            }
            else if (defaults.RoundBased)
            {
                foreach (int rounds in new[] { 2, 3, 4, 5, 6, 7 })
                {
                    _limits.Add(rounds);
                    limitNames.Add(rounds + " rounds (best of " + (rounds * 2 - 1) + ")");
                }
            }
            else
            {
                int[] options = mode == GameModeKind.Domination ? new[] { 100, 150, 200, 300 }
                    : mode == GameModeKind.Hardpoint ? new[] { 100, 150, 200, 250 }
                    : mode == GameModeKind.FreeForAll ? new[] { 3, 5, 10, 15, 20, 25 }
                    : new[] { 3, 5, 10, 20, 30, 50 };
                string unit = defaults.UsesZones ? " points" : " kills";
                foreach (int limit in options)
                {
                    _limits.Add(limit);
                    limitNames.Add(limit + unit);
                }
            }
            int wanted = PlayerPrefs.GetInt(LimitKey + mode, defaults.RoundBased ? defaults.roundsToWin : defaults.scoreLimit);
            SetChoices(_limitField, limitNames, Mathf.Max(0, _limits.IndexOf(wanted)));

            // Time: a round's length in round modes, the whole match's otherwise.
            _times.Clear();
            var timeNames = new List<string>();
            float[] times = defaults.RoundBased ? new[] { 60f, 90f, 120f, 180f } : new[] { 300f, 600f, 900f, 1200f };
            foreach (float seconds in times)
            {
                _times.Add(seconds);
                timeNames.Add(defaults.RoundBased ? seconds + " seconds a round" : seconds / 60f + " minutes");
            }
            float defaultTime = defaults.RoundBased ? defaults.roundSeconds : defaults.timeLimitSeconds;
            SetChoices(_timeField, timeNames, Mathf.Max(0, _times.IndexOf(PlayerPrefs.GetFloat(TimeKey + mode, defaultTime))));
            _timeField.label = defaults.RoundBased ? "Round time" : "Time limit";

            // Respawning only happens in modes that respawn.
            _respawnField.style.display = defaults.RoundBased ? DisplayStyle.None : DisplayStyle.Flex;
            _respawnField.index = Mathf.Max(0, Array.IndexOf(RespawnChoices, PlayerPrefs.GetFloat(RespawnKey + mode, defaults.respawnSeconds)));
            if (Array.IndexOf(RespawnChoices, PlayerPrefs.GetFloat(RespawnKey + mode, defaults.respawnSeconds)) < 0) _respawnField.index = 1;
            // Gun Game hands out its own weapons.
            _weaponsField.SetEnabled(mode != GameModeKind.GunGame);
        }

        static void SetChoices(DropdownField field, List<string> choices, int index)
        {
            field.choices = choices;
            field.index = choices.Count > 0 ? Mathf.Clamp(index, 0, choices.Count - 1) : -1;
            field.SetEnabled(choices.Count > 1);
        }

        MatchSettings BuildSettings()
        {
            GameModeKind mode = SelectedMode;
            MatchSettings settings = MatchSettings.For(mode);
            if (_mapField.index >= 0 && _mapField.index < _mapIds.Count) settings.arenaId = _mapIds[_mapField.index];
            if (_sizeField.index >= 0 && _sizeField.index < _sizes.Count)
            {
                if (settings.TeamBased) settings.teamSize = _sizes[_sizeField.index];
                else settings.maxPlayers = _sizes[_sizeField.index];
            }
            if (_limitField.index >= 0 && _limitField.index < _limits.Count)
            {
                if (settings.RoundBased) settings.roundsToWin = _limits[_limitField.index];
                else settings.scoreLimit = _limits[_limitField.index];
            }
            int bots = Mathf.Clamp(_botsField.index, 0, 3);
            settings.fillWithBots = bots > 0;
            settings.botSkill = Mathf.Max(0, bots - 1);
            if (_timeField.index >= 0 && _timeField.index < _times.Count)
            {
                if (settings.RoundBased) settings.roundSeconds = _times[_timeField.index];
                else settings.timeLimitSeconds = _times[_timeField.index];
            }
            settings.maxHealth = HealthChoices[Mathf.Clamp(_healthField.index, 0, HealthChoices.Length - 1)];
            if (!settings.RoundBased) settings.respawnSeconds = RespawnChoices[Mathf.Clamp(_respawnField.index, 0, RespawnChoices.Length - 1)];
            if (mode != GameModeKind.GunGame) settings.weapons = WeaponRules.All[Mathf.Clamp(_weaponsField.index, 0, WeaponRules.All.Length - 1)];
            return settings;
        }

        void Remember()
        {
            GameModeKind mode = SelectedMode;
            PlayerPrefs.SetInt(ModeKey, Array.IndexOf(Modes, mode));
            PlayerPrefs.SetInt(BotsKey, _botsField.index);
            PlayerPrefs.SetInt(HealthKey, HealthChoices[Mathf.Clamp(_healthField.index, 0, HealthChoices.Length - 1)]);
            PlayerPrefs.SetInt(WeaponsKey, Mathf.Max(0, _weaponsField.index));
            if (_timeField.index >= 0 && _timeField.index < _times.Count) PlayerPrefs.SetFloat(TimeKey + mode, _times[_timeField.index]);
            PlayerPrefs.SetFloat(RespawnKey + mode, RespawnChoices[Mathf.Clamp(_respawnField.index, 0, RespawnChoices.Length - 1)]);
            if (_mapField.index >= 0 && _mapField.index < _mapIds.Count) PlayerPrefs.SetString(MapKey + mode, _mapIds[_mapField.index]);
            if (_sizeField.index >= 0 && _sizeField.index < _sizes.Count) PlayerPrefs.SetInt(SizeKey + mode, _sizes[_sizeField.index]);
            if (_limitField.index >= 0 && _limitField.index < _limits.Count) PlayerPrefs.SetInt(LimitKey + mode, _limits[_limitField.index]);
            PlayerPrefs.SetString(NameKey, PlayerName);
        }

        void RequestJoin()
        {
            string address = _addressField.value.Trim();
            if (address.Length == 0) return;
            PlayerPrefs.SetString(AddressKey, address);
            Remember();
            JoinRequested?.Invoke(address);
        }

        // ------------------------------------------------------------------ the match overlay

        void BuildMatch(VisualElement root)
        {
            _match = new VisualElement();
            _match.AddToClassList("layer");
            _match.pickingMode = PickingMode.Ignore;
            Fill(_match);
            root.Add(_match);

            // Scores, round and clock across the top; the zones under them.
            var top = new VisualElement { pickingMode = PickingMode.Ignore };
            top.style.position = Position.Absolute;
            top.style.top = 18;
            top.style.left = 0;
            top.style.right = 0;
            top.style.alignItems = Align.Center;
            _match.Add(top);

            var scores = Row(top);
            scores.style.justifyContent = Justify.Center;
            scores.style.alignItems = Align.Center;

            _nameLeft = Text_("", 18, Text, bold: true);
            _nameLeft.style.width = 260;
            _nameLeft.style.unityTextAlign = TextAnchor.MiddleRight;
            _scoreLeft = Text_("0", 40, Accent, bold: true);
            _scoreLeft.style.minWidth = 84;
            _scoreLeft.style.unityTextAlign = TextAnchor.MiddleCenter;

            var middle = new VisualElement();
            middle.style.width = 150;
            middle.style.alignItems = Align.Center;
            middle.pickingMode = PickingMode.Ignore;
            _clock = Text_("", 24, Text, bold: true);
            _round = Text_("", 12, Dim, bold: true, spacing: 3);
            middle.Add(_clock);
            middle.Add(_round);

            _scoreRight = Text_("0", 40, Bad, bold: true);
            _scoreRight.style.minWidth = 84;
            _scoreRight.style.unityTextAlign = TextAnchor.MiddleCenter;
            _nameRight = Text_("", 18, Text, bold: true);
            _nameRight.style.width = 260;

            scores.Add(_nameLeft);
            scores.Add(_scoreLeft);
            scores.Add(middle);
            scores.Add(_scoreRight);
            scores.Add(_nameRight);

            _zoneStrip = Row(top);
            _zoneStrip.style.marginTop = 6;
            _zoneStrip.style.justifyContent = Justify.Center;

            // Announcements, a quarter of the way down.
            var banner = new VisualElement();
            banner.pickingMode = PickingMode.Ignore;
            banner.style.position = Position.Absolute;
            banner.style.top = Length.Percent(24);
            banner.style.left = 0;
            banner.style.right = 0;
            banner.style.alignItems = Align.Center;
            _bannerTitle = Text_("", 64, Text, bold: true, spacing: 8);
            _bannerTitle.AddToClassList("banner-pop");
            _bannerSub = Text_("", 20, Dim);
            _notice = Text_("", 15, Accent);
            _notice.style.marginTop = 10;
            banner.Add(_bannerTitle);
            banner.Add(_bannerSub);
            banner.Add(_notice);
            _match.Add(banner);

            // Medals, under the crosshair.
            var medal = new VisualElement { pickingMode = PickingMode.Ignore };
            medal.AddToClassList("medal");
            medal.AddToClassList("medal--hidden");
            _medal = Text_("", 26, new Color32(255, 214, 92, 255), bold: true, spacing: 4);
            _medalLine = Text_("", 15, Text, spacing: 2);
            _medal.style.unityTextAlign = TextAnchor.MiddleCenter;
            _medalLine.style.unityTextAlign = TextAnchor.MiddleCenter;
            medal.Add(_medal);
            medal.Add(_medalLine);
            _match.Add(medal);

            BuildChat();

            // Who took us out, low in the middle while we wait to come back.
            _death = new VisualElement { pickingMode = PickingMode.Ignore };
            _death.style.position = Position.Absolute;
            _death.style.bottom = 170;
            _death.style.left = 0;
            _death.style.right = 0;
            _death.style.alignItems = Align.Center;
            _deathTitle = Text_("", 24, Bad, bold: true, spacing: 3);
            _deathLine = Text_("", 15, Text);
            _death.Add(_deathTitle);
            _death.Add(_deathLine);
            _death.style.display = DisplayStyle.None;
            _match.Add(_death);

            // A line for respawns and Gun Game, above the weapons along the bottom centre.
            _status = Text_("", 15, Accent, bold: true, spacing: 1);
            _status.style.position = Position.Absolute;
            _status.style.bottom = 118;
            _status.style.left = 0;
            _status.style.right = 0;
            _status.style.unityTextAlign = TextAnchor.MiddleCenter;
            _match.Add(_status);

            // Health, bottom left: the weapons have the bottom centre.
            var health = new VisualElement();
            health.pickingMode = PickingMode.Ignore;
            health.style.position = Position.Absolute;
            health.style.bottom = 28;
            health.style.left = 28;
            health.style.alignItems = Align.FlexStart;
            health.style.paddingLeft = health.style.paddingRight = 16;
            health.style.paddingTop = 10;
            health.style.paddingBottom = 14;
            health.style.backgroundColor = new Color(0.04f, 0.055f, 0.08f, 0.55f);
            health.style.borderLeftWidth = 3;
            health.style.borderLeftColor = Good;
            Round(health, 6);
            Label healthTitle = Text_("HEALTH", 12, Dim, bold: true, spacing: 3);
            _healthText = Text_("100", 30, Text, bold: true);
            var bar = new VisualElement();
            bar.pickingMode = PickingMode.Ignore;
            bar.style.width = 240;
            bar.style.height = 8;
            bar.style.marginTop = 2;
            bar.style.backgroundColor = new Color(0.04f, 0.06f, 0.08f, 0.7f);
            Round(bar, 4);
            _healthFill = new VisualElement();
            _healthFill.pickingMode = PickingMode.Ignore;
            _healthFill.style.height = Length.Percent(100);
            _healthFill.style.width = Length.Percent(100);
            _healthFill.style.backgroundColor = Good;
            Round(_healthFill, 4);
            bar.Add(_healthFill);
            health.Add(healthTitle);
            health.Add(_healthText);
            health.Add(bar);
            _match.Add(health);

            // Kill feed, top right.
            _feedBox = new VisualElement();
            _feedBox.pickingMode = PickingMode.Ignore;
            _feedBox.style.position = Position.Absolute;
            _feedBox.style.top = 28;
            _feedBox.style.right = 28;
            _feedBox.style.alignItems = Align.FlexEnd;
            _match.Add(_feedBox);

            // Connection readout, top left.
            _netStats = Text_("", 13, Dim);
            _netStats.style.position = Position.Absolute;
            _netStats.style.top = 28;
            _netStats.style.left = 28;
            _netStats.style.whiteSpace = WhiteSpace.Normal;
            _match.Add(_netStats);

            BuildScoreboard();
        }

        void BuildScoreboard()
        {
            _scoreboard = new VisualElement { pickingMode = PickingMode.Ignore };
            Fill(_scoreboard);
            _scoreboard.style.alignItems = Align.Center;
            _scoreboard.style.justifyContent = Justify.Center;
            _scoreboard.style.display = DisplayStyle.None;
            _match.Add(_scoreboard);

            var card = new VisualElement { pickingMode = PickingMode.Ignore };
            card.style.minWidth = 620;
            card.style.paddingLeft = card.style.paddingRight = 22;
            card.style.paddingTop = card.style.paddingBottom = 18;
            card.style.backgroundColor = new Color(0.05f, 0.07f, 0.1f, 0.92f);
            card.style.borderTopWidth = 3;
            card.style.borderTopColor = Accent;
            Round(card, 8);
            _scoreboard.Add(card);

            _scoreboardTitle = Text_("", 15, Dim, bold: true, spacing: 3);
            _scoreboardTitle.style.marginBottom = 10;
            card.Add(_scoreboardTitle);
            _scoreboardBody = new VisualElement { pickingMode = PickingMode.Ignore };
            card.Add(_scoreboardBody);
        }

        // ------------------------------------------------------------------ profile and ranked

        /// <summary>Ranked is chosen, and allowed: the mode has it, and the player is signed in with a verified email.</summary>
        bool RankedChosen => _rankedToggle != null && _rankedToggle.value && RankedAllowed(out _);

        bool RankedAllowed(out string why)
        {
            why = "";
            if (!Playlists.HasRanked(SelectedMode))
            {
                why = "Ranked is Duel and Elimination.";
                return false;
            }
            if (_services == null || !_services.Account.SignedIn)
            {
                why = "Sign in to play ranked.";
                return false;
            }
            if (!_services.Account.Account.emailVerified)
            {
                why = "Verify your email address to play ranked.";
                return false;
            }
            if (_services.Social != null && _services.Social.InParty)
            {
                why = "Ranked is played alone. Leave the party to queue for it.";
                return false;
            }
            return true;
        }

        /// <summary>In a party, only the leader finds matches; everyone else follows.</summary>
        bool PartyMember => _services != null && _services.Social != null && _services.Social.InParty && !_services.Social.IsLeader;

        void OnSocialChanged()
        {
            RefreshRanked();
            RefreshFind();
        }

        void RefreshFind()
        {
            if (_findButton == null) return;
            _findButton.SetEnabled(!_busy && !PartyMember);
            _findButton.text = PartyMember ? "Your party leader finds the match" : _services != null && _services.Social != null && _services.Social.InParty
                ? "Find match for the party" : "Find match";
        }

        void RefreshRanked()
        {
            if (_rankedToggle == null) return;
            bool allowed = RankedAllowed(out string why);
            _rankedToggle.SetEnabled(allowed);
            if (!allowed)
            {
                _rankedToggle.SetValueWithoutNotify(false);
                _rankedHint.text = why;
                return;
            }
            Playlist playlist = Playlists.For(SelectedMode, true);
            RankData rank = ProgressionCache.Rank(playlist.Id);
            _rankedHint.text = _rankedToggle.value
                ? playlist.Title + ": " + rank.name + (rank.placementLeft > 0 ? "" : "  (" + rank.rating + ")") + ". Full matches of people, matched by rating."
                : "Your " + playlist.Title + " rank: " + rank.name;
        }

        /// <summary>Level and XP across the top of the menu, for a signed-in player; an invitation to sign in otherwise.</summary>
        void BuildProfile(VisualElement card)
        {
            _profile = new VisualElement();
            _profile.style.flexDirection = FlexDirection.Row;
            _profile.style.alignItems = Align.Center;
            _profile.style.marginBottom = 12;
            _profile.style.paddingLeft = _profile.style.paddingRight = 12;
            _profile.style.paddingTop = _profile.style.paddingBottom = 8;
            _profile.style.backgroundColor = new Color(0.1f, 0.13f, 0.18f, 1f);
            Round(_profile, 6);
            card.Add(_profile);

            _levelText = Text_("", 18, Accent, bold: true, spacing: 1);
            _levelText.style.minWidth = 92;
            _profile.Add(_levelText);

            var bars = new VisualElement();
            bars.style.flexGrow = 1;
            bars.style.marginRight = 12;
            _profile.Add(bars);
            var track = new VisualElement();
            track.style.height = 8;
            track.style.backgroundColor = new Color(0.04f, 0.06f, 0.08f, 1f);
            Round(track, 4);
            _xpFill = new VisualElement();
            _xpFill.style.height = Length.Percent(100);
            _xpFill.style.backgroundColor = Accent;
            Round(_xpFill, 4);
            track.Add(_xpFill);
            bars.Add(track);
            _xpText = Text_("", 12, Dim);
            _xpText.style.marginTop = 3;
            _xpText.style.whiteSpace = WhiteSpace.Normal;
            bars.Add(_xpText);

            _progressButton = MenuButton("Progress", false, () => ProgressRequested?.Invoke());
            _progressButton.style.marginLeft = 0;
            _progressButton.style.minWidth = 110;
            _profile.Add(_progressButton);

            ProgressionCache.Changed += RefreshProfile;
            if (_services != null) _services.Account.Changed += RefreshProfile;
            RefreshProfile();
        }

        void RefreshProfile()
        {
            if (_profile == null) return;
            ProgressionData progression = ProgressionCache.Current;
            bool signedIn = _services != null && _services.Account.SignedIn;
            _xpFill.parent.style.display = signedIn ? DisplayStyle.Flex : DisplayStyle.None;
            _progressButton.style.display = signedIn ? DisplayStyle.Flex : DisplayStyle.None;
            if (!signedIn)
            {
                _levelText.text = "GUEST";
                _xpText.text = "Sign in to earn XP, unlock weapons, take on challenges and play ranked.";
            }
            else if (progression == null)
            {
                _levelText.text = "LEVEL -";
                _xpText.text = "Fetching your progress...";
                _xpFill.style.width = Length.Percent(0);
            }
            else
            {
                LevelData level = progression.level;
                bool max = level.level >= level.maxLevel;
                _levelText.text = "LEVEL " + level.level;
                float fraction = max || level.xpForNextLevel <= 0 ? 1f : Mathf.Clamp01(level.xpIntoLevel / (float)level.xpForNextLevel);
                _xpFill.style.width = Length.Percent(fraction * 100f);
                int open = 0;
                foreach (ChallengeData challenge in progression.challenges) if (!challenge.completed) open++;
                _xpText.text = (max ? "Top level" : level.xpIntoLevel + " / " + level.xpForNextLevel + " XP to level " + (level.level + 1)) +
                               "   ·   " + open + " challenge(s) to do";
            }
            RefreshRanked();
        }

        // ------------------------------------------------------------------ menu

        /// <summary>
        /// Shows the menu, ready for input. <paramref name="status"/> is a line of bad news, or
        /// empty. Coming back from a match, the menu opens on its home screen; otherwise it
        /// stays on the page the player was using, so a problem is shown where it happened.
        /// </summary>
        public void ShowMenu(string status)
        {
            if (_menu == null) return;
            bool wasHidden = _menu.style.display == DisplayStyle.None;
            _menu.style.display = DisplayStyle.Flex;
            SetBusy(false);
            if (wasHidden) ShowPage(Page.Home);
            SetStatus(status, Bad);
            Cursor.lockState = CursorLockMode.None;
            Cursor.visible = true;
        }

        /// <summary>Shows the menu's home screen with a line of good news, such as how the last match went.</summary>
        public void ShowMenuResult(string text)
        {
            ShowMenu("");
            if (_page != Page.Home) ShowPage(Page.Home);
            SetStatus(text, Good);
        }

        /// <summary>Shows the play page with its buttons off while a match is being found or joined.</summary>
        public void ShowConnecting(string status)
        {
            if (_menu == null) return;
            _menu.style.display = DisplayStyle.Flex;
            if (_page != Page.Play) ShowPage(Page.Play);
            SetStatus(status, Text);
            SetBusy(true);
        }

        public void HideMenu()
        {
            if (_menu == null) return;
            _menu.style.display = DisplayStyle.None;
            PlayerPrefs.SetString(NameKey, PlayerName);
        }

        public bool MenuVisible => _menu != null && _menu.resolvedStyle.display != DisplayStyle.None;

        /// <summary>The menu's line of news, on both pages so it is seen whichever is up.</summary>
        void SetStatus(string text, Color color)
        {
            foreach (Label label in new[] { _menuStatus, _homeStatus })
            {
                if (label == null) continue;
                label.text = text ?? "";
                label.style.color = color;
            }
        }

        void SetBusy(bool busy)
        {
            _busy = busy;
            RefreshFind();
            _hostToggle.SetEnabled(!busy);
            _startButton.SetEnabled(!busy);
            _joinButton.SetEnabled(!busy);
            _rangeButton.SetEnabled(!busy);
            _customizeButton.SetEnabled(!busy);
            _playButton.SetEnabled(!busy);
            _backButton.SetEnabled(!busy);
            _modeGrid.SetEnabled(!busy);
            _nameField.SetEnabled(!busy);
            _addressField.SetEnabled(!busy);
            _modeField.SetEnabled(!busy);
            _rankedToggle.SetEnabled(!busy && RankedAllowed(out _));
            _progressButton.SetEnabled(!busy);
            _cancelButton.style.display = busy ? DisplayStyle.Flex : DisplayStyle.None;
        }

        /// <summary>Esc on the play page goes back to the home screen, unless it was meant for a screen open on top.</summary>
        void UpdateMenuKeys()
        {
            bool overlayOpen = SettingsScreen.IsOpen || CustomizeScreen.IsOpen || ProgressScreen.IsOpen ||
                               PlayersScreen.IsOpen || ReportDialog.IsOpen || TextEntry.Active;
            // A screen that closed on this same Esc counts as still open, so one press does one thing.
            bool blocked = overlayOpen || _overlayOpenLastFrame;
            _overlayOpenLastFrame = overlayOpen;
            if (blocked || !MenuVisible || _busy || _page != Page.Play) return;
            Keyboard keyboard = Keyboard.current;
            if (keyboard != null && keyboard.escapeKey.wasPressedThisFrame) ShowPage(Page.Home);
        }

        // ------------------------------------------------------------------ match

        /// <summary>Takes the match overlay off screen without forgetting what it shows, while a menu is up.</summary>
        public void SetMatchHidden(bool hidden)
        {
            if (_match != null) _match.style.visibility = hidden ? Visibility.Hidden : Visibility.Visible;
        }

        public void ShowMatch(bool visible)
        {
            if (_match == null) return;
            _match.style.display = visible ? DisplayStyle.Flex : DisplayStyle.None;
            if (visible) return;
            ShowDeath(null, null);
            CloseChat();
            foreach (Label line in _chat) line.RemoveFromHierarchy();
            _chat.Clear();
            _chatAge.Clear();
            foreach (Label line in _feed) line.RemoveFromHierarchy();
            _feed.Clear();
            _feedAge.Clear();
            ShowScoreboard(false);
            SetZones(null, 0, -1, Teams.None, false);
        }

        /// <summary>Our side on the left, the other on the right.</summary>
        public void SetScore(string ourName, string ourScore, string theirName, string theirScore, string round, string clock)
        {
            if (_match == null) return;
            _nameLeft.text = ourName;
            _scoreLeft.text = ourScore;
            _nameRight.text = theirName;
            _scoreRight.text = theirScore;
            _round.text = round;
            _clock.text = clock;
        }

        /// <summary>
        /// The zones under the score. Domination shows every zone; Hardpoint only the one in
        /// play. A zone's colour is its holder's; the fill shows a capture under way, or for a
        /// hardpoint the time it has left.
        /// </summary>
        public void SetZones(ZoneState[] zones, int count, int activeZone, int ourTeam, bool hardpoint, string[] names = null)
        {
            if (_zoneStrip == null) return;
            int shown = hardpoint ? (activeZone >= 0 && activeZone < count ? 1 : 0) : count;
            while (_zoneBadges.Count < shown) _zoneBadges.Add(MakeZoneBadge());
            for (int i = 0; i < _zoneBadges.Count; i++)
                _zoneBadges[i].Box.style.display = i < shown ? DisplayStyle.Flex : DisplayStyle.None;

            bool blink = Mathf.Repeat(Time.unscaledTime, 0.5f) < 0.25f;
            for (int i = 0; i < shown; i++)
            {
                int index = hardpoint ? activeZone : i;
                ZoneState zone = zones[index];
                Zone badge = _zoneBadges[i];
                string name = names != null && index < names.Length ? names[index] : ((char)('A' + index)).ToString();
                badge.Letter.text = hardpoint ? name.ToUpperInvariant() : name;
                badge.Box.style.minWidth = hardpoint ? 150 : 38;

                badge.Box.style.backgroundColor = TeamColor(zone.Owner, ourTeam, 0.85f, new Color(0.1f, 0.12f, 0.16f, 0.8f));
                Color edge = zone.Contested && blink ? Color.white : new Color(1f, 1f, 1f, 0.25f);
                badge.Box.style.borderTopColor = badge.Box.style.borderBottomColor =
                    badge.Box.style.borderLeftColor = badge.Box.style.borderRightColor = edge;

                if (hardpoint)
                {
                    badge.Fill.style.height = 3;
                    badge.Fill.style.width = Length.Percent(Mathf.Clamp01(zone.Progress) * 100f);
                    badge.Fill.style.backgroundColor = Color.white;
                }
                else
                {
                    badge.Fill.style.width = Length.Percent(100);
                    badge.Fill.style.height = Length.Percent(Mathf.Clamp01(zone.Progress) * 100f);
                    badge.Fill.style.backgroundColor = TeamColor(zone.Capturer, ourTeam, 0.7f, Color.clear);
                }
            }
        }

        Zone MakeZoneBadge()
        {
            var box = new VisualElement { pickingMode = PickingMode.Ignore };
            box.style.height = 38;
            box.style.marginLeft = box.style.marginRight = 4;
            box.style.justifyContent = Justify.Center;
            box.style.alignItems = Align.Center;
            box.style.borderTopWidth = box.style.borderBottomWidth = box.style.borderLeftWidth = box.style.borderRightWidth = 2;
            box.style.overflow = Overflow.Hidden;
            Round(box, 6);

            var fill = new VisualElement { pickingMode = PickingMode.Ignore };
            fill.style.position = Position.Absolute;
            fill.style.left = 0;
            fill.style.bottom = 0;
            box.Add(fill);

            Label letter = Text_("", 18, Text, bold: true);
            letter.style.paddingLeft = letter.style.paddingRight = 8;
            box.Add(letter);
            _zoneStrip.Add(box);
            return new Zone { Box = box, Fill = fill, Letter = letter };
        }

        /// <summary>Our colour, theirs, or a fallback for nobody.</summary>
        public static Color TeamColor(int team, int ourTeam, float alpha, Color nobody)
        {
            if (team == Teams.None || team < 0) return nobody;
            Color color = team == ourTeam ? Accent : Bad;
            color.a = alpha;
            return color;
        }

        public void SetHealth(float current, float max)
        {
            if (_match == null) return;
            float fraction = max > 0f ? Mathf.Clamp01(current / max) : 0f;
            _healthText.text = Mathf.CeilToInt(Mathf.Max(current, 0f)).ToString();
            _healthFill.style.width = Length.Percent(fraction * 100f);
            _healthFill.style.backgroundColor = Color.Lerp(Bad, Good, Mathf.InverseLerp(0.2f, 0.6f, fraction));
        }

        /// <summary>The line over the health bar: respawn timer, Gun Game progress. Empty clears it.</summary>
        public void SetStatus(string text)
        {
            if (_match != null) _status.text = text ?? "";
        }

        /// <summary>The big announcement in the middle of the screen. Empty strings clear it.</summary>
        public void SetBanner(string title, string subtitle, bool good = true)
        {
            if (_match == null) return;
            if (!string.IsNullOrEmpty(title) && title != _bannerTitle.text) UiMotion.Pop(_bannerTitle, "banner-pop--start");
            _bannerTitle.text = title ?? "";
            _bannerTitle.style.color = good ? Text : Bad;
            _bannerSub.text = subtitle ?? "";
        }

        /// <summary>A small line under the banner, for things worth knowing but not shouting.</summary>
        public void SetNotice(string text)
        {
            if (_match != null) _notice.text = text ?? "";
        }

        public void SetNetStats(string text)
        {
            if (_match != null) _netStats.text = text ?? "";
        }

        public void AddKill(string text, FeedTone tone)
        {
            if (_match == null) return;
            Label line = Text_(text, 15, tone == FeedTone.Ours ? Good : tone == FeedTone.Theirs ? Bad : Text, bold: true);
            line.style.paddingLeft = 10;
            line.style.paddingRight = 10;
            line.style.paddingTop = 4;
            line.style.paddingBottom = 4;
            line.style.marginBottom = 4;
            line.style.backgroundColor = Panel;
            Round(line, 4);
            _feedBox.Add(line);
            UiMotion.Enter(line);
            _feed.Add(line);
            _feedAge.Add(0f);

            if (_feed.Count <= KillFeedLines) return;
            _feed[0].RemoveFromHierarchy();
            _feed.RemoveAt(0);
            _feedAge.RemoveAt(0);
        }

        // ------------------------------------------------------------------ scoreboard

        public bool ScoreboardVisible => _scoreboard != null && _scoreboard.style.display == DisplayStyle.Flex;

        public void ShowScoreboard(bool visible)
        {
            if (_scoreboard != null) _scoreboard.style.display = visible ? DisplayStyle.Flex : DisplayStyle.None;
        }

        /// <summary>
        /// Fills the scoreboard: by team (ours first) in team modes, one list otherwise, each
        /// sorted best first. <paramref name="scoreLabel"/> heads the last column.
        /// </summary>
        public void SetScoreboard(string title, List<ScoreRow> rows, bool teams, int ourTeam, string scoreLabel, int score0 = 0, int score1 = 0)
        {
            if (_scoreboardBody == null) return;
            _scoreboardTitle.text = title;
            _scoreboardBody.Clear();
            rows.Sort((a, b) => b.Score != a.Score ? b.Score.CompareTo(a.Score) : b.Kills != a.Kills ? b.Kills.CompareTo(a.Kills) : a.Deaths.CompareTo(b.Deaths));

            if (!teams)
            {
                AddHeader("PLAYERS", Text, scoreLabel);
                for (int i = 0; i < rows.Count; i++) AddRow(rows[i], (i + 1) + ".", rows[i].Local ? Accent : Text);
                return;
            }

            for (int pass = 0; pass < 2; pass++)
            {
                int team = pass == 0 ? ourTeam : 1 - ourTeam;
                if (team < 0 || team > 1) team = pass;
                Color color = team == ourTeam ? Accent : Bad;
                AddHeader((team == ourTeam ? "YOUR TEAM" : "ENEMY TEAM") + "   " + (team == 0 ? score0 : score1), color, scoreLabel);
                foreach (ScoreRow row in rows)
                {
                    if (row.Team == team) AddRow(row, "", row.Local ? Accent : Text);
                }
                if (pass == 0) _scoreboardBody.Add(new VisualElement { style = { height = 12 } });
            }
        }

        void AddHeader(string title, Color color, string scoreLabel)
        {
            VisualElement line = Row(_scoreboardBody);
            line.style.borderBottomWidth = 1;
            line.style.borderBottomColor = new Color(1f, 1f, 1f, 0.15f);
            line.style.paddingBottom = 3;
            line.style.marginBottom = 3;
            Cell(line, title, 300, color, bold: true, left: true);
            Cell(line, "K", 60, Dim, bold: true);
            Cell(line, "D", 60, Dim, bold: true);
            Cell(line, scoreLabel, 110, Dim, bold: true);
        }

        void AddRow(in ScoreRow row, string prefix, Color color)
        {
            VisualElement line = Row(_scoreboardBody);
            line.style.paddingTop = line.style.paddingBottom = 2;
            if (row.Local) line.style.backgroundColor = new Color(Accent.r, Accent.g, Accent.b, 0.12f);
            string name = (prefix.Length > 0 ? prefix + " " : "") + row.Name + (row.Bot ? "  (bot)" : "");
            Cell(line, name, 300, row.Alive ? color : new Color(color.r, color.g, color.b, 0.5f), bold: row.Local, left: true);
            Cell(line, row.Kills.ToString(), 60, Text);
            Cell(line, row.Deaths.ToString(), 60, Text);
            Cell(line, row.Score.ToString(), 110, Text, bold: true);
        }

        static void Cell(VisualElement line, string text, float width, Color color, bool bold = false, bool left = false)
        {
            Label label = Text_(text, 15, color, bold);
            label.style.width = width;
            label.style.unityTextAlign = left ? TextAnchor.MiddleLeft : TextAnchor.MiddleCenter;
            line.Add(label);
        }

        void OnDestroy()
        {
            _account?.Dispose();
            _social?.Dispose();
            if (_services != null && _services.Social != null) _services.Social.Changed -= OnSocialChanged;
            ProgressionCache.Changed -= RefreshProfile;
            if (_services != null) _services.Account.Changed -= RefreshProfile;
        }

        // ------------------------------------------------------------------ chat

        /// <summary>Someone typed something to send: the text, and whether it is for the team only.</summary>
        public event Action<string, bool> ChatSubmitted;

        /// <summary>The chat box is open for typing.</summary>
        public bool ChatOpen => _chatField != null && _chatField.style.display == DisplayStyle.Flex;

        void BuildChat()
        {
            // Bottom left, above the health panel.
            _chatBox = new VisualElement { pickingMode = PickingMode.Ignore };
            _chatBox.style.position = Position.Absolute;
            _chatBox.style.left = 28;
            _chatBox.style.bottom = 132;
            _chatBox.style.width = 560;
            _match.Add(_chatBox);

            _chatLines = new VisualElement { pickingMode = PickingMode.Ignore };
            _chatBox.Add(_chatLines);

            var row = Row(_chatBox);
            row.style.alignItems = Align.Center;
            row.style.marginTop = 4;
            _chatScope = Text_("ALL", 13, Accent, bold: true, spacing: 2);
            _chatScope.style.width = 52;
            row.Add(_chatScope);
            _chatField = new TextField { maxLength = Shared.Social.ChatText.MaxLength };
            _chatField.style.flexGrow = 1;
            _chatField.style.fontSize = 15;
            _chatField.RegisterCallback<KeyDownEvent>(OnChatKey, TrickleDown.TrickleDown);
            row.Add(_chatField);
            _chatScope.style.display = DisplayStyle.None;
            _chatField.style.display = DisplayStyle.None;
        }

        /// <summary>Opens the box to type in: to everyone, or to the team.</summary>
        public void OpenChat(bool team)
        {
            if (_chatField == null || ChatOpen) return;
            _chatTeam = team;
            _chatScope.text = team ? "TEAM" : "ALL";
            _chatScope.style.color = team ? (Color)new Color32(96, 190, 255, 255) : Accent;
            _chatScope.style.display = DisplayStyle.Flex;
            _chatField.style.display = DisplayStyle.Flex;
            _chatField.SetValueWithoutNotify("");
            TextEntry.Active = true;
            ShowChatLines(true);
            _chatField.schedule.Execute(() =>
            {
                _chatField.SetValueWithoutNotify("");       // the key that opened it is not part of the message
                _chatField.Focus();
            }).StartingIn(16);
        }

        public void CloseChat()
        {
            if (_chatField == null) return;
            _chatField.Blur();
            _chatField.style.display = DisplayStyle.None;
            _chatScope.style.display = DisplayStyle.None;
            ShowChatLines(false);
            // Let go of the keyboard a frame later, so the Enter that sent the line does not also do something in play.
            _chatField.schedule.Execute(() => TextEntry.Active = false).StartingIn(16);
        }

        void OnChatKey(KeyDownEvent e)
        {
            if (e.keyCode == KeyCode.Return || e.keyCode == KeyCode.KeypadEnter)
            {
                string text = _chatField.value;
                CloseChat();
                if (!string.IsNullOrWhiteSpace(text)) ChatSubmitted?.Invoke(text, _chatTeam);
                e.StopPropagation();
            }
            else if (e.keyCode == KeyCode.Escape)
            {
                CloseChat();
                e.StopPropagation();
            }
        }

        /// <summary>Adds a line: who said it, coloured by side, and what.</summary>
        public void AddChat(string speaker, string text, Color speakerColor, bool teamOnly)
        {
            if (_chatLines == null) return;
            var line = new Label { pickingMode = PickingMode.Ignore, enableRichText = false };
            line.style.whiteSpace = WhiteSpace.Normal;
            line.style.fontSize = 15;
            line.style.color = Text;
            line.style.paddingLeft = line.style.paddingRight = 8;
            line.style.paddingTop = line.style.paddingBottom = 2;
            line.style.marginTop = 2;
            line.style.backgroundColor = new Color(0.03f, 0.04f, 0.06f, 0.5f);
            Round(line, 4);
            line.text = (teamOnly ? "[TEAM] " : "") + speaker + ":  " + text;
            line.style.borderLeftWidth = 3;
            line.style.borderLeftColor = speakerColor;
            _chatLines.Add(line);
            _chat.Add(line);
            _chatAge.Add(0f);
            UiMotion.Enter(line);
            while (_chat.Count > 30)
            {
                _chat[0].RemoveFromHierarchy();
                _chat.RemoveAt(0);
                _chatAge.RemoveAt(0);
            }
            ShowChatLines(ChatOpen);
        }

        /// <summary>A grey line from the game itself, such as who was muted.</summary>
        public void AddChatNotice(string text) => AddChat("", text, new Color(1f, 1f, 1f, 0.3f), false);

        void ShowChatLines(bool all)
        {
            for (int i = 0; i < _chat.Count; i++)
            {
                bool recent = i >= _chat.Count - ChatLinesShown;
                bool fresh = _chatAge[i] < ChatSeconds;
                _chat[i].style.display = recent && (all || fresh) ? DisplayStyle.Flex : DisplayStyle.None;
                _chat[i].style.opacity = all ? 1f : Mathf.Clamp01(ChatSeconds - _chatAge[i]);
            }
        }

        void UpdateChat()
        {
            if (_chat.Count == 0) return;
            for (int i = 0; i < _chatAge.Count; i++) _chatAge[i] += Time.unscaledDeltaTime;
            ShowChatLines(ChatOpen);
        }

        /// <summary>A medal under the crosshair: a headshot, a multi-kill, a streak. It shows for a moment and goes.</summary>
        public void ShowMedal(string title, string line = "")
        {
            if (_match == null) return;
            _medal.text = title ?? "";
            _medalLine.text = line ?? "";
            VisualElement box = _medal.parent;
            box.RemoveFromClassList("medal--hidden");
            UiMotion.Pop(box, "medal--hidden");
            _medalTimer = 1.8f;
        }

        /// <summary>Who took us out, with what, and how much health they had left. Null hides it.</summary>
        public void ShowDeath(string title, string line)
        {
            if (_match == null) return;
            if (title == null)
            {
                _death.style.display = DisplayStyle.None;
                return;
            }
            _deathTitle.text = title;
            _deathLine.text = line ?? "";
            _death.style.display = DisplayStyle.Flex;
            UiMotion.Enter(_death);
        }

        void Update()
        {
            UpdateChat();
            UpdateMenuKeys();
            if (_medalTimer > 0f)
            {
                _medalTimer -= Time.unscaledDeltaTime;
                if (_medalTimer <= 0f && _medal != null) _medal.parent.AddToClassList("medal--hidden");
            }

            // Kill feed lines fade out and go.
            for (int i = _feed.Count - 1; i >= 0; i--)
            {
                _feedAge[i] += Time.unscaledDeltaTime;
                _feed[i].style.opacity = Mathf.Clamp01(KillFeedSeconds - _feedAge[i]);
                if (_feedAge[i] < KillFeedSeconds) continue;
                _feed[i].RemoveFromHierarchy();
                _feed.RemoveAt(i);
                _feedAge.RemoveAt(i);
            }
        }

        // ------------------------------------------------------------------ helpers

        static Label Text_(string text, int size, Color color, bool bold = false, int spacing = 0, string className = null)
        {
            var label = new Label(text) { pickingMode = PickingMode.Ignore };
            label.style.fontSize = size;
            label.style.color = color;
            if (bold) label.style.unityFontStyleAndWeight = FontStyle.Bold;
            if (spacing > 0) label.style.letterSpacing = spacing;
            if (className != null) label.AddToClassList(className);
            return label;
        }

        static Button MenuButton(string text, bool primary, Action onClick)
        {
            var button = new Button(onClick) { text = text };
            button.AddToClassList("pause-button");
            if (primary)
            {
                button.AddToClassList("primary");
                button.style.marginLeft = 0;
                button.style.height = 46;
            }
            return button;
        }

        static VisualElement Row(VisualElement parent)
        {
            var row = new VisualElement { pickingMode = PickingMode.Ignore };
            row.style.flexDirection = FlexDirection.Row;
            parent.Add(row);
            return row;
        }

        /// <summary>Stretches an element over the whole of its parent.</summary>
        static void Fill(VisualElement element)
        {
            element.style.position = Position.Absolute;
            element.style.left = 0;
            element.style.top = 0;
            element.style.right = 0;
            element.style.bottom = 0;
        }

        static void Round(VisualElement element, float radius)
        {
            element.style.borderTopLeftRadius = radius;
            element.style.borderTopRightRadius = radius;
            element.style.borderBottomLeftRadius = radius;
            element.style.borderBottomRightRadius = radius;
        }
    }
}
