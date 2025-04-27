/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  transpilePackages: [
    "antd",
    "@ant-design",
    "rc-util",
    "rc-pagination",
    "rc-picker",
    "rc-notification",
    "rc-tooltip",
    "rc-tree",
    "rc-table",
    "@rc-component/util",
    "@rc-component/pagination",
    "@rc-component/picker",
    "@rc-component/notification",
    "@rc-component/tooltip",
    "@rc-component/tree",
    "@rc-component/table"
  ],
}

module.exports = nextConfig; 