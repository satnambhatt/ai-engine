CLONE_REPOS=$1

clone_html_css() {
  cd /mnt/design-library/example-websites/html-css/
  git clone https://github.com/zce/html5up.git
  git clone https://github.com/StartBootstrap/startbootstrap-agency
  git clone https://github.com/StartBootstrap/startbootstrap-creative
  git clone https://github.com/tailwindtoolbox/Landing-Page
}

clone_react() {
  cd /mnt/design-library/example-websites/react/
  git clone https://github.com/shadcn-ui/taxonomy
  git clone https://github.com/steven-tey/dub             # SaaS landing
  git clone https://github.com/cruip/open-react-template
}

clone_nextjs() {
  cd /mnt/design-library/example-websites/nextjs/
  git clone https://github.com/vercel/commerce nextjs-commerce
  git clone https://github.com/mickasmt/next-saas-stripe-starter
}

clone_astro() {
  cd /mnt/design-library/example-websites/astro/
  git clone https://github.com/onwidget/astrowind
  git clone https://github.com/satnaing/astro-paper
  git clone https://github.com/withastro/starlight
}

clone_tailwind() {
  cd /mnt/design-library/example-websites/tailwind/
  git clone https://github.com/markmead/hyperui
  git clone https://github.com/tailwindlabs/tailwindcss.com
}

clone_multi_page() {
  cd /mnt/design-library/example-websites/multi-page-sites/
  git clone https://github.com/RyanFitzgerald/devportfolio
}

case $CLONE_REPOS in
  all)
    clone_html_css
    clone_react
    clone_nextjs
    clone_astro
    clone_tailwind
    clone_multi_page
  ;;

  html)
    clone_html_css
  ;;

  nextjs)
    clone_nextjs
  ;;

  astro)
    clone_astro
  ;;

  tailwind)
    clone_tailwind
  ;;

  multipage)
    clone_multi_page
  ;;

  *)
    echo "Usage of this script"
    echo "chmod +x clone-sample-repos.sh" 
    echo "./clone-sample-repos.sh OPTIONS"
    echo "OPTIONS: all, html, nextjs, astro, tailwind, multipage"
  ;;
esac