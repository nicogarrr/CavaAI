'use client';

import { useState } from 'react';

const faqs = [
  {
    question: "Is OpenStock really free forever?",
    answer: "Yes! We're part of the Open Dev Society, which means we'll never lock knowledge behind paywalls. Core features remain free always. We run on community donations and the belief that financial tools should be accessible to everyone."
  },
  {
    question: "I'm a student - can I use this for my projects?",
    answer: "Absolutely! That's exactly why we built this. Use it for school projects, learning, or building your portfolio. Need help? Our community loves mentoring students. Email student@opendevsociety.org for extra support."
  },
  {
    question: "How do I add stocks to my favorites?",
    answer: "Navigate to any stock page and click the star icon. You can also search using the search bar and add directly from results. Everything is designed to be intuitive - no complex tutorials needed."
  },
  {
    question: "Can I contribute to OpenStock?",
    answer: "We'd love that! OpenStock is open source and community-driven. Check our GitHub for issues marked 'good first issue' or 'help wanted'. Every contribution, no matter how small, makes a difference."
  },
  {
    question: "What if I find a bug or have a feature request?",
    answer: "Please tell us! Submit issues on GitHub, join our Discord, or email opendevsociety@gmail.com. We see every report as a chance to make the platform better for everyone."
  }
];

export default function HelpTabs() {
  const [activeTab, setActiveTab] = useState<'faq' | 'api' | 'community'>('faq');

  return (
    <div className="container mx-auto px-4 py-12 max-w-4xl">
      <div className="text-center mb-12">
        <h1 className="text-4xl font-bold text-gray-100 mb-4">Help Center</h1>
        <p className="text-xl text-gray-200 mb-4">
          Free help, API documentation, and community support
        </p>
        <div className="bg-green-300 border border-green-200 rounded-lg p-4 max-w-2xl mx-auto">
          <p className="text-black text-sm">
            🤝 <strong>Our Promise:</strong> Every question matters. Every beginner is welcomed. No exclusion, ever.
          </p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 mb-8 border-b border-gray-700">
        <button
          onClick={() => setActiveTab('faq')}
          className={`px-6 py-3 font-medium transition-colors ${
            activeTab === 'faq'
              ? 'text-teal-400 border-b-2 border-teal-400'
              : 'text-gray-400 hover:text-gray-300'
          }`}
        >
          FAQs
        </button>
        <button
          onClick={() => setActiveTab('api')}
          className={`px-6 py-3 font-medium transition-colors ${
            activeTab === 'api'
              ? 'text-teal-400 border-b-2 border-teal-400'
              : 'text-gray-400 hover:text-gray-300'
          }`}
        >
          API Docs
        </button>
        <button
          onClick={() => setActiveTab('community')}
          className={`px-6 py-3 font-medium transition-colors ${
            activeTab === 'community'
              ? 'text-teal-400 border-b-2 border-teal-400'
              : 'text-gray-400 hover:text-gray-300'
          }`}
        >
          Community
        </button>
      </div>

      {/* FAQ Tab */}
      {activeTab === 'faq' && (
        <>
          {/* Help Philosophy */}
          <div className="grid md:grid-cols-3 gap-6 mb-12">
            <div className="bg-gray-800 rounded-lg shadow-sm p-6 border hover:shadow-md transition-shadow">
              <h3 className="text-lg font-semibold text-blue-500 mb-2">Learn Together</h3>
              <p className="text-gray-200 text-sm">
                Every expert was once a beginner. Our guides are written by the community, for the community.
                No jargon, no assumptions about prior knowledge.
              </p>
            </div>

            <div className="bg-gray-800 rounded-lg shadow-sm p-6 border hover:shadow-md transition-shadow">
              <h3 className="text-lg font-semibold text-green-500 mb-2">Community Support</h3>
              <p className="text-gray-200 text-sm">
                Real people helping real people. Our Discord community includes students, professionals,
                and mentors who genuinely want to help you succeed.
              </p>
            </div>

            <div className="bg-gray-800 rounded-lg shadow-sm p-6 border hover:shadow-md transition-shadow">
              <h3 className="text-lg font-semibold text-purple-500 mb-2">Built with Care</h3>
              <p className="text-gray-200 text-sm">
                Every feature is designed with accessibility and ease-of-use in mind.
                We believe powerful tools should be simple to use.
              </p>
            </div>
          </div>

          {/* Community FAQs */}
          <section className="mb-12">
            <h2 className="text-3xl font-bold text-gray-100 mb-8 text-center">Community Questions</h2>
            <div className="space-y-4">
              {faqs.map((faq, index) => (
                <div key={index} className="bg-gray-800 rounded-lg shadow-sm p-6 border">
                  <h3 className="text-lg font-semibold text-gray-100 mb-2">{faq.question}</h3>
                  <p className="text-gray-200">{faq.answer}</p>
                </div>
              ))}
            </div>
          </section>
        </>
      )}

      {/* API Docs Tab */}
      {activeTab === 'api' && (
        <div className="space-y-8">
          <div className="mb-8">
            <h2 className="text-3xl font-bold text-gray-100 mb-4">Free & Open API Documentation</h2>
            <p className="text-xl text-gray-200 mb-4">
              Complete guide to integrating with the OpenStock API - completely free, forever
            </p>
            <div className="bg-blue-300 border border-blue-400 rounded-lg p-4">
              <p className="text-black text-sm">
                💡 <strong>Open Dev Society Promise:</strong> This API will always be free. No hidden costs, no usage limits for personal projects, no barriers to knowledge.
              </p>
            </div>
          </div>

          {/* Philosophy */}
          <section className="bg-gray-800 rounded-lg shadow-sm p-6 border">
            <h2 className="text-2xl font-semibold text-gray-100 mb-4">🌍 Our API Philosophy</h2>
            <p className="text-gray-200 mb-4">
              We believe market data should be accessible to everyone - students building their first portfolio tracker,
              developers creating tools for their community, and anyone who wants to learn about finance without barriers.
            </p>
            <ul className="text-gray-200 space-y-2">
              <li>✅ <strong>Always Free:</strong> Core features remain free forever</li>
              <li>✅ <strong>No Gatekeeping:</strong> Simple authentication, clear documentation</li>
              <li>✅ <strong>Community First:</strong> Built for learners, students, and builders</li>
              <li>✅ <strong>Open Source:</strong> API examples and SDKs are open source</li>
            </ul>
          </section>

          {/* Community Support */}
          <section className="bg-gray-800 rounded-lg shadow-sm p-6 border">
            <h2 className="text-2xl font-semibold text-gray-100 mb-4">🤝 Community & Support</h2>
            <div className="grid md:grid-cols-2 gap-4">
              <div className="bg-green-200 p-4 rounded-lg">
                <h3 className="font-semibold text-black mb-2">🎓 For Students</h3>
                <p className="text-gray-800 text-sm">
                  Building a project for class? Email us at <strong>opendevsociety@cc.cc</strong> for unlimited access and mentorship.
                </p>
              </div>
              <div className="bg-blue-300 p-4 rounded-lg">
                <h3 className="font-semibold text-black mb-2">💻 For Developers</h3>
                <p className="text-gray-800 text-sm">
                  Join our Discord community for code examples, troubleshooting, and collaboration opportunities.
                </p>
              </div>
            </div>
          </section>

          {/* Open Source Commitment */}
          <section className="bg-gray-800 rounded-lg p-6 border">
            <h2 className="text-2xl font-semibold text-gray-200 mb-4">🔓 Open Source Promise</h2>
            <p className="text-gray-200 mb-4">
              This API, its documentation, and all example code are open source.
              Found a bug? Want a feature? Submit a PR or issue on GitHub.
            </p>
            <div className="flex space-x-4">
              <a target="_blank" rel="noopener noreferrer" href="https://github.com/Open-Dev-Society/"
                 className="bg-gray-200 text-gray-800 px-4 py-2 rounded hover:bg-gray-300 transition-colors">
                Contact us
              </a>
            </div>
          </section>
        </div>
      )}

      {/* Community Tab */}
      {activeTab === 'community' && (
        <section className="bg-gradient-to-r from-blue-200 to-purple-200 rounded-lg p-8 text-center">
          <h2 className="text-2xl font-bold text-gray-900 mb-4">Join Our Community</h2>
          <p className="text-gray-700 mb-6">
            Don&apos;t struggle alone. Our community of builders, learners, and dreamers is here to help.
            Because we believe the future belongs to those who build it openly.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
              <a
                  href="https://discord.gg/jdJuEMvk"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="bg-blue-600 text-white px-6 py-3 rounded-lg hover:bg-blue-550 transition-colors text-center inline-block"
              >
                  Join Discord Community
              </a>

              <a
                  href="mailto:opendevsociety@gmail.com"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="bg-gray-800 text-gray-200 px-6 py-3 rounded-lg hover:bg-gray-900 transition-colors text-center inline-block"
              >
                  Email Help Team
              </a>
          </div>
          <p className="text-xs text-gray-600 mt-4">
            ✨ All support is free, always. We&apos;re here because we care, not for profit.
          </p>
        </section>
      )}
    </div>
  );
}

