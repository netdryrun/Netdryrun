/* Click-to-load YouTube embeds. Nothing is fetched from YouTube or Google until the visitor clicks play:
   the poster is a file on this site, and the iframe (youtube-nocookie.com) is created only on click.

   Usage in a Markdown page (the poster goes in docs/assets/video/, never a YouTube thumbnail URL):

   <figure class="ndr-yt" data-video-id="VIDEO_ID_11_CHARS" data-title="What the video shows">
   <button type="button" class="ndr-yt__play" aria-label="Play the video: What the video shows. Loads YouTube.">
   <img src="/assets/video/POSTER.jpg" alt="" width="1280" height="720" loading="lazy">
   <span class="ndr-yt__badge">Play · loads YouTube</span>
   </button>
   <figcaption>One line on what it shows. <a href="https://www.youtube.com/watch?v=VIDEO_ID_11_CHARS">Watch on YouTube</a>.</figcaption>
   </figure>

   Before the first embed goes live, add a line to privacy.md: playing an embedded video loads it from
   YouTube (youtube-nocookie.com), which then receives the visitor's IP address and browser details. */
document.addEventListener("click", function (event) {
  var button = event.target.closest(".ndr-yt__play");
  if (!button) return;
  var figure = button.closest(".ndr-yt");
  var id = figure && figure.getAttribute("data-video-id");
  if (!id || !/^[A-Za-z0-9_-]{11}$/.test(id)) return;
  var frame = document.createElement("iframe");
  frame.src = "https://www.youtube-nocookie.com/embed/" + id + "?autoplay=1&rel=0";
  frame.title = figure.getAttribute("data-title") || "Video";
  frame.allow = "autoplay; encrypted-media; picture-in-picture; fullscreen";
  frame.allowFullscreen = true;
  frame.referrerPolicy = "strict-origin-when-cross-origin";
  frame.className = "ndr-yt__frame";
  button.replaceWith(frame);
  frame.focus();
});
